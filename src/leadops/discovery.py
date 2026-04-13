from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess

from leadops.approaches import ApproachSpec
from leadops.config import WorkspaceConfig
from leadops.models import (
    DiscoveryBatch,
    DiscoveryCandidate,
    discovery_batch_from_dict,
    drop_stacked_opportunity_mismatch_candidate,
    drop_stale_public_signal_candidate,
)
from leadops.query_plans import QueryTrack
from leadops.repository import Repository


@dataclass(slots=True)
class DiscoveryRunResult:
    query_run_id: int
    created: int
    updated: int
    total_candidates: int


@dataclass(slots=True)
class DiscoveryTrackQueryResult:
    query_name: str
    query_text: str
    kind: str
    created: int
    updated: int
    total_candidates: int
    query_run_id: int


@dataclass(slots=True)
class DiscoveryTrackResult:
    track_name: str
    results: list[DiscoveryTrackQueryResult]

    @property
    def total_created(self) -> int:
        return sum(item.created for item in self.results)

    @property
    def total_updated(self) -> int:
        return sum(item.updated for item in self.results)

    @property
    def total_candidates(self) -> int:
        return sum(item.total_candidates for item in self.results)


def discover_web(
    repo: Repository,
    config: WorkspaceConfig,
    *,
    query: str,
    kind: str,
    limit: int,
    source: str,
    approach: ApproachSpec | None = None,
) -> DiscoveryRunResult:
    if config.discovery.provider != "command":
        raise RuntimeError("Discovery is not configured. Set [discovery] provider = \"command\" first.")
    if not config.discovery.command:
        raise RuntimeError("Discovery command provider selected but no command is configured.")

    query_run_id = repo.start_query_run(query_text=query, kind=kind, provider=config.discovery.provider)
    payload = {
        "profile": {
            "name": config.profile.name,
            "offer": config.profile.offer,
            "base_location": config.profile.base_location,
            "service_geography": config.profile.service_geography,
            "ideal_customer": config.profile.ideal_customer,
            "fit_definition": config.profile.fit_definition,
            "preferred_signals": config.profile.preferred_signals,
            "caution_signals": config.profile.caution_signals,
            "post_contact_checks": config.profile.post_contact_checks,
            "hard_rejects": config.profile.hard_rejects,
        },
        "approach": approach.as_payload() if approach else {},
        "feedback": repo.feedback_context_payload(),
        "search": {
            "kind": kind,
            "query": query,
            "limit": limit,
        },
    }

    try:
        batch = _discover_with_command(config, payload)
        stale_filtered = 0
        mismatch_filtered = 0
        candidates: list[DiscoveryCandidate] = []
        for candidate in batch.candidates:
            if drop_stale_public_signal_candidate(candidate):
                stale_filtered += 1
                continue
            if drop_stacked_opportunity_mismatch_candidate(candidate):
                mismatch_filtered += 1
                continue
            candidates.append(candidate)
            if len(candidates) >= max(1, limit):
                break
        created = 0
        updated = 0
        for candidate in candidates:
            target_id, action = repo.add_or_update_target(
                kind=kind,
                name=candidate.name,
                url=candidate.url,
                source=source,
                notes=candidate.notes_text(),
                raw_evidence=candidate.raw_evidence_text(),
                reactivate_expired=_should_reactivate_expired(candidate),
            )
            repo.add_query_run_target(
                query_run_id=query_run_id,
                target_id=target_id,
                action=action,
                candidate=candidate,
            )
            if action == "created":
                created += 1
            else:
                updated += 1

        notes = f"candidates={len(candidates)} created={created} updated={updated}"
        if stale_filtered:
            notes += f" filtered_stale_public={stale_filtered}"
        if mismatch_filtered:
            notes += f" filtered_mismatch={mismatch_filtered}"
        if len(batch.candidates) > max(1, limit):
            notes += f" provider_candidates={len(batch.candidates)} truncated=true"
        repo.finish_query_run(
            query_run_id,
            status="done",
            notes=notes,
            raw_json=json.dumps(batch.raw_response, indent=2),
        )
        return DiscoveryRunResult(
            query_run_id=query_run_id,
            created=created,
            updated=updated,
            total_candidates=len(candidates),
        )
    except Exception as exc:
        repo.finish_query_run(query_run_id, status="failed", notes=str(exc))
        raise


def discover_track(
    repo: Repository,
    config: WorkspaceConfig,
    *,
    track: QueryTrack,
    limit_override: int | None = None,
    source_prefix: str = "web-discovery",
    approach: ApproachSpec | None = None,
) -> DiscoveryTrackResult:
    results: list[DiscoveryTrackQueryResult] = []
    for spec in track.queries:
        result = discover_web(
            repo,
            config,
            query=spec.query,
            kind=spec.kind,
            limit=limit_override if limit_override is not None else spec.default_limit,
            source=f"{source_prefix}:{track.name}:{spec.name}",
            approach=approach,
        )
        results.append(
            DiscoveryTrackQueryResult(
                query_name=spec.name,
                query_text=spec.query,
                kind=spec.kind,
                created=result.created,
                updated=result.updated,
                total_candidates=result.total_candidates,
                query_run_id=result.query_run_id,
            )
        )
    return DiscoveryTrackResult(track_name=track.name, results=results)


def _discover_with_command(config: WorkspaceConfig, payload: dict[str, object]) -> DiscoveryBatch:
    completed = subprocess.run(
        config.discovery.command,
        input=json.dumps(payload),
        capture_output=True,
        check=False,
        text=True,
        timeout=config.discovery.timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Discovery command failed with exit code {completed.returncode}: {completed.stderr.strip()}"
        )
    raw = json.loads(completed.stdout)
    return discovery_batch_from_dict(raw)


def _should_reactivate_expired(candidate: DiscoveryCandidate) -> bool:
    return (
        candidate.activation_signal == "explicit"
        and candidate.freshness == "fresh"
        and candidate.evidence_confidence in {"strong", "moderate"}
        and candidate.profile_fit in {"high", "medium"}
    )
