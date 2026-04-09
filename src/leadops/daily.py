from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from leadops.briefs import BriefItem, render_email_subject, write_packet
from leadops.config import WorkspaceConfig
from leadops.mailer import send_email_digest
from leadops.models import AssessmentResult
from leadops.providers import CommandProvider, MockProvider
from leadops.repository import Repository, TargetRecord


@dataclass(slots=True)
class DailyRunResult:
    packet_markdown: Path
    packet_json: Path
    digest_text: Path
    surfaced_new: int
    surfaced_followups: int
    packet_id: int
    run_id: int
    digest_sent: bool


def run_daily(
    repo: Repository,
    config: WorkspaceConfig,
    packet_date: str,
    *,
    send_digest: bool = False,
) -> DailyRunResult:
    provider = _provider_for_config(config)
    run_id = repo.start_run(packet_date)
    notes: list[str] = []
    try:
        cooldown_cutoff = (date.fromisoformat(packet_date) - timedelta(days=config.profile.cooldown_days)).isoformat()
        feedback_context = repo.feedback_context_payload()

        candidate_items = _assess_candidates(
            repo=repo,
            targets=repo.list_candidate_targets(),
            provider=provider,
            config=config,
            run_id=run_id,
            cooldown_cutoff=cooldown_cutoff,
            daily_cap=config.profile.daily_new_lead_cap,
            section="new_target",
            feedback_context=feedback_context,
        )
        followup_items = _assess_followups(
            repo=repo,
            targets=repo.list_due_followups(packet_date),
            provider=provider,
            config=config,
            run_id=run_id,
            daily_cap=config.profile.daily_followup_cap,
            feedback_context=feedback_context,
        )

        packet_dir = config.outbox_dir / packet_date
        markdown_path, json_path, digest_path = write_packet(packet_dir, packet_date, candidate_items, followup_items)
        packet_id = repo.create_packet(run_id, packet_date, markdown_path, json_path)

        for item in candidate_items + followup_items:
            assessment_id = repo.save_assessment(run_id, item.target.id, provider.name, item.assessment)
            repo.add_packet_item(
                packet_id=packet_id,
                target_id=item.target.id,
                assessment_id=assessment_id,
                section=item.section,
                rank_index=item.rank_index,
                score=item.assessment.fit_score,
                confidence=item.assessment.confidence,
            )
            repo.mark_packeted(item.target.id, packet_date)

        notes.append(f"new_targets={len(candidate_items)}")
        notes.append(f"followups_due={len(followup_items)}")
        digest_sent = False
        if send_digest or config.email.send_on_run:
            send_email_digest(
                email_config=config.email,
                subject=render_email_subject(packet_date, candidate_items, followup_items),
                body=digest_path.read_text(encoding="utf-8"),
            )
            digest_sent = True
            notes.append("digest_sent=true")
        repo.finish_run(run_id, status="done", notes=", ".join(notes))
        return DailyRunResult(
            packet_markdown=markdown_path,
            packet_json=json_path,
            digest_text=digest_path,
            surfaced_new=len(candidate_items),
            surfaced_followups=len(followup_items),
            packet_id=packet_id,
            run_id=run_id,
            digest_sent=digest_sent,
        )
    except Exception as exc:
        repo.finish_run(run_id, status="failed", notes=str(exc))
        raise


def _assess_candidates(
    *,
    repo: Repository,
    targets: list[TargetRecord],
    provider: CommandProvider | MockProvider,
    config: WorkspaceConfig,
    run_id: int,
    cooldown_cutoff: str,
    daily_cap: int,
    section: str,
    feedback_context: dict[str, list[dict[str, str]]],
) -> list[BriefItem]:
    eligible: list[tuple[TargetRecord, AssessmentResult]] = []
    for target in targets:
        if target.last_packeted_at and target.last_packeted_at > cooldown_cutoff:
            continue
        assessment = provider.assess(target, config, feedback_context)
        if not assessment.recommend:
            repo.save_assessment(run_id, target.id, provider.name, assessment)
            continue
        eligible.append((target, assessment))

    eligible.sort(key=lambda item: (item[1].fit_score, item[1].confidence), reverse=True)
    return [
        BriefItem(target=target, assessment=assessment, section=section, rank_index=index)
        for index, (target, assessment) in enumerate(eligible[:daily_cap], start=1)
    ]


def _assess_followups(
    *,
    repo: Repository,
    targets: list[TargetRecord],
    provider: CommandProvider | MockProvider,
    config: WorkspaceConfig,
    run_id: int,
    daily_cap: int,
    feedback_context: dict[str, list[dict[str, str]]],
) -> list[BriefItem]:
    items: list[tuple[TargetRecord, AssessmentResult]] = []
    for target in targets:
        assessment = provider.assess(target, config, feedback_context)
        assessment.why_now = "This follow-up is already due or overdue."
        assessment.draft_subject = f"Following up on {target.name}"
        items.append((target, assessment))
    items.sort(key=lambda item: (item[0].next_followup_at or "", -item[1].fit_score))
    return [
        BriefItem(target=target, assessment=assessment, section="followup", rank_index=index)
        for index, (target, assessment) in enumerate(items[:daily_cap], start=1)
    ]


def _provider_for_config(config: WorkspaceConfig) -> CommandProvider | MockProvider:
    if config.llm.provider == "command":
        return CommandProvider()
    return MockProvider()
