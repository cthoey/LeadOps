from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json

from leadops.models import AssessmentResult
from leadops.repository import TargetRecord
from leadops.util import write_text


@dataclass(slots=True)
class BriefItem:
    target: TargetRecord
    assessment: AssessmentResult
    section: str
    rank_index: int


def render_markdown(packet_date: str, new_items: list[BriefItem], followup_items: list[BriefItem]) -> str:
    lines = [
        f"# LeadOps Daily Brief - {packet_date}",
        "",
        f"- New targets: {len(new_items)}",
        f"- Follow-ups due: {len(followup_items)}",
        "",
    ]
    lines.extend(_render_section("New High-Fit Targets", new_items))
    lines.extend(_render_section("Follow-Ups Due", followup_items))
    return "\n".join(lines).rstrip() + "\n"


def render_email_subject(packet_date: str, new_items: list[BriefItem], followup_items: list[BriefItem]) -> str:
    return f"LeadOps Daily Brief - {packet_date} ({len(new_items)} new, {len(followup_items)} follow-ups)"


def render_email_text(packet_date: str, new_items: list[BriefItem], followup_items: list[BriefItem]) -> str:
    lines = [
        f"LeadOps Daily Brief - {packet_date}",
        "",
        f"New targets: {len(new_items)}",
        f"Follow-ups due: {len(followup_items)}",
        "",
    ]
    lines.extend(_render_email_section("New High-Fit Targets", new_items))
    lines.extend(_render_email_section("Follow-Ups Due", followup_items))
    return "\n".join(lines).rstrip() + "\n"


def write_packet(
    packet_dir: Path,
    packet_date: str,
    new_items: list[BriefItem],
    followup_items: list[BriefItem],
) -> tuple[Path, Path, Path]:
    packet_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = packet_dir / "daily-brief.md"
    json_path = packet_dir / "daily-brief.json"
    digest_path = packet_dir / "daily-digest.txt"

    markdown = render_markdown(packet_date, new_items, followup_items)
    digest_text = render_email_text(packet_date, new_items, followup_items)
    payload = {
        "packet_date": packet_date,
        "new_targets": [_item_to_dict(item) for item in new_items],
        "followups_due": [_item_to_dict(item) for item in followup_items],
    }

    write_text(markdown_path, markdown)
    write_text(json_path, json.dumps(payload, indent=2) + "\n")
    write_text(digest_path, digest_text)
    return markdown_path, json_path, digest_path


def _render_section(title: str, items: list[BriefItem]) -> list[str]:
    lines = [f"## {title}", ""]
    if not items:
        lines.extend(["None today.", ""])
        return lines

    for item in items:
        target = item.target
        assessment = item.assessment
        lines.extend(
            [
                f"### {item.rank_index}. {target.name}",
                "",
                f"- Kind: `{target.kind}`",
                f"- Source: `{target.source}`",
                f"- URL: {target.url or 'n/a'}",
                f"- Score: `{assessment.fit_score:.1f}`",
                f"- Confidence: `{assessment.confidence:.2f}`",
                f"- Why fit: {assessment.why_fit}",
                f"- Why now: {assessment.why_now}",
                f"- Outreach angle: {assessment.outreach_angle}",
                "",
                "Draft subject:",
                "",
                "```text",
                assessment.draft_subject,
                "```",
                "",
                "Draft body:",
                "",
                "```text",
                assessment.draft_body,
                "```",
                "",
            ]
        )
        if assessment.evidence:
            lines.append("Evidence:")
            lines.append("")
            for evidence in assessment.evidence:
                lines.append(f"- {evidence}")
            lines.append("")
        if assessment.risks:
            lines.append("Risks:")
            lines.append("")
            for risk in assessment.risks:
                lines.append(f"- {risk}")
            lines.append("")
    return lines


def _item_to_dict(item: BriefItem) -> dict:
    return {
        "rank_index": item.rank_index,
        "section": item.section,
        "target": {
            "id": item.target.id,
            "kind": item.target.kind,
            "name": item.target.name,
            "url": item.target.url,
            "source": item.target.source,
            "status": item.target.status,
            "notes": item.target.notes,
            "next_followup_at": item.target.next_followup_at,
        },
        "assessment": item.assessment.as_dict(),
    }


def _render_email_section(title: str, items: list[BriefItem]) -> list[str]:
    lines = [title, "-" * len(title)]
    if not items:
        lines.extend(["None today.", ""])
        return lines

    for item in items:
        target = item.target
        assessment = item.assessment
        lines.extend(
            [
                f"{item.rank_index}. {target.name} [{target.kind}]",
                f"   Source: {target.source}",
                f"   URL: {target.url or 'n/a'}",
                f"   Score / confidence: {assessment.fit_score:.1f} / {assessment.confidence:.2f}",
                f"   Why fit: {assessment.why_fit}",
                f"   Why now: {assessment.why_now}",
                f"   Subject: {assessment.draft_subject}",
                "",
            ]
        )
    return lines
