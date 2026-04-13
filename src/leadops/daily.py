from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from leadops.approaches import ApproachSpec
from leadops.briefs import BriefItem, render_email_subject, write_packet
from leadops.config import WorkspaceConfig
from leadops.mailer import send_email_digest
from leadops.models import (
    ACTION_QUEUE_ORDER,
    ACTIVATION_SIGNAL_RANK,
    EVIDENCE_CONFIDENCE_RANK,
    FRESHNESS_RANK,
    PROFILE_FIT_RANK,
    VISIBLE_CANDIDATE_QUEUES,
    AssessmentResult,
    apply_stacked_opportunity_mismatch_guard,
    apply_stale_public_signal_guard,
)
from leadops.providers import CommandProvider, MockProvider
from leadops.repository import Repository, TargetRecord

DEFAULT_CANDIDATE_ASSESSMENT_WINDOW_MULTIPLIER = 4
MIN_CANDIDATE_ASSESSMENT_WINDOW = 12


@dataclass(slots=True)
class DailyRunResult:
    packet_markdown: Path
    packet_json: Path
    digest_text: Path
    digest_html: Path
    current_review_markdown: Path
    current_review_json: Path
    current_review_text: Path
    current_review_html: Path
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
    approach: ApproachSpec | None = None,
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
            targets=repo.list_candidate_targets(packet_date),
            provider=provider,
            config=config,
            run_id=run_id,
            cooldown_cutoff=cooldown_cutoff,
            daily_cap=config.profile.daily_new_lead_cap,
            approach=approach,
            feedback_context=feedback_context,
        )
        followup_items = _assess_followups(
            repo=repo,
            targets=repo.list_due_followups(packet_date),
            provider=provider,
            config=config,
            run_id=run_id,
            daily_cap=config.profile.daily_followup_cap,
            approach=approach,
            feedback_context=feedback_context,
        )

        packet_dir = config.outbox_dir / packet_date
        packet_version = repo.next_packet_version(packet_date)
        markdown_path, json_path, digest_path, digest_html_path = write_packet(
            packet_dir,
            config.review_dir,
            packet_date,
            candidate_items,
            followup_items,
            approach=approach,
            version=packet_version,
        )

        notes.append(f"pursue_now={sum(1 for item in candidate_items if item.section == 'pursue_now')}")
        notes.append(f"watch={sum(1 for item in candidate_items if item.section == 'watch')}")
        notes.append(f"nurture={sum(1 for item in candidate_items if item.section == 'nurture')}")
        notes.append(f"followup_due={len(followup_items)}")
        if approach:
            notes.append(f"approach={approach.name}")
        digest_sent = False
        if send_digest or config.email.send_on_run:
            send_email_digest(
                email_config=config.email,
                subject=render_email_subject(packet_date, candidate_items, followup_items),
                body_text=digest_path.read_text(encoding="utf-8"),
                body_html=digest_html_path.read_text(encoding="utf-8"),
            )
            digest_sent = True
            notes.append("digest_sent=true")
        packet_id = repo.create_packet(run_id, packet_date, markdown_path, json_path, version=packet_version)

        for item in candidate_items + followup_items:
            assessment_id = repo.save_assessment(run_id, item.target.id, provider.name, item.assessment)
            repo.add_packet_item(
                packet_id=packet_id,
                target_id=item.target.id,
                assessment_id=assessment_id,
                section=item.section,
                rank_index=item.rank_index,
                score=item.assessment.priority_score,
                confidence=item.assessment.confidence,
            )
            repo.mark_packeted(item.target.id, packet_date)
        repo.finish_run(run_id, status="done", notes=", ".join(notes))
        return DailyRunResult(
            packet_markdown=markdown_path,
            packet_json=json_path,
            digest_text=digest_path,
            digest_html=digest_html_path,
            current_review_markdown=config.review_dir / "current-review.md",
            current_review_json=config.review_dir / "current-review.json",
            current_review_text=config.review_dir / "current-review.txt",
            current_review_html=config.review_dir / "current-review.html",
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
    approach: ApproachSpec | None,
    feedback_context: dict[str, list[dict[str, str]]],
) -> list[BriefItem]:
    candidate_window = max(daily_cap * DEFAULT_CANDIDATE_ASSESSMENT_WINDOW_MULTIPLIER, MIN_CANDIDATE_ASSESSMENT_WINDOW)
    eligible: list[tuple[TargetRecord, AssessmentResult]] = []
    for target in targets[:candidate_window]:
        if target.last_packeted_at and target.last_packeted_at > cooldown_cutoff:
            continue
        assessment = provider.assess(target, config, approach, feedback_context)
        apply_stale_public_signal_guard(assessment)
        apply_stacked_opportunity_mismatch_guard(assessment)
        if assessment.action_queue not in VISIBLE_CANDIDATE_QUEUES:
            repo.save_assessment(run_id, target.id, provider.name, assessment)
            continue
        eligible.append((target, assessment))

    eligible.sort(key=lambda item: _candidate_sort_key(item[1]))
    selected = eligible[:daily_cap]
    return [
        BriefItem(target=target, assessment=assessment, section=assessment.action_queue, rank_index=index)
        for index, (target, assessment) in enumerate(selected, start=1)
    ]


def _assess_followups(
    *,
    repo: Repository,
    targets: list[TargetRecord],
    provider: CommandProvider | MockProvider,
    config: WorkspaceConfig,
    run_id: int,
    daily_cap: int,
    approach: ApproachSpec | None,
    feedback_context: dict[str, list[dict[str, str]]],
) -> list[BriefItem]:
    items: list[tuple[TargetRecord, AssessmentResult]] = []
    for target in targets:
        assessment = provider.assess(target, config, approach, feedback_context)
        assessment.action_queue = "followup_due"
        assessment.activation_rationale = "This follow-up is already due or overdue."
        if not assessment.draft_subject.strip():
            assessment.draft_subject = f"Following up on {target.name}"
        if not assessment.draft_body.strip():
            assessment.draft_body = f"Checking back in on {target.name} now that the scheduled follow-up is due."
        items.append((target, assessment))
    items.sort(key=lambda item: (item[0].next_followup_at or "", _followup_sort_key(item[1])))
    return [
        BriefItem(target=target, assessment=assessment, section="followup_due", rank_index=index)
        for index, (target, assessment) in enumerate(items[:daily_cap], start=1)
    ]


def _provider_for_config(config: WorkspaceConfig) -> CommandProvider | MockProvider:
    if config.llm.provider == "command":
        return CommandProvider()
    return MockProvider()


def _candidate_sort_key(assessment: AssessmentResult) -> tuple[int, int, int, int, float, float]:
    return (
        ACTION_QUEUE_ORDER.get(assessment.action_queue, 9),
        -PROFILE_FIT_RANK.get(assessment.profile_fit, 0),
        -ACTIVATION_SIGNAL_RANK.get(assessment.activation_signal, 0),
        -EVIDENCE_CONFIDENCE_RANK.get(assessment.evidence_confidence, 0),
        -FRESHNESS_RANK.get(assessment.freshness, 0),
        -assessment.priority_score,
        -assessment.confidence,
    )


def _followup_sort_key(assessment: AssessmentResult) -> tuple[int, int, int, int, float]:
    return (
        -PROFILE_FIT_RANK.get(assessment.profile_fit, 0),
        -ACTIVATION_SIGNAL_RANK.get(assessment.activation_signal, 0),
        -EVIDENCE_CONFIDENCE_RANK.get(assessment.evidence_confidence, 0),
        -FRESHNESS_RANK.get(assessment.freshness, 0),
        -assessment.priority_score,
    )
