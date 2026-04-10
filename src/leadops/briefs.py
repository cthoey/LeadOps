from __future__ import annotations

from dataclasses import dataclass
from html import escape
from pathlib import Path
import json

from leadops.approaches import ApproachSpec
from leadops.models import AssessmentResult
from leadops.repository import TargetRecord
from leadops.util import write_text


@dataclass(slots=True)
class BriefItem:
    target: TargetRecord
    assessment: AssessmentResult
    section: str
    rank_index: int


def render_markdown(
    packet_date: str,
    new_items: list[BriefItem],
    followup_items: list[BriefItem],
    *,
    approach: ApproachSpec | None = None,
) -> str:
    lines = [
        f"# LeadOps Daily Brief - {packet_date}",
        "",
        f"- New targets: {len(new_items)}",
        f"- Follow-ups due: {len(followup_items)}",
        "",
    ]
    lines.extend(_render_markdown_context(approach))
    lines.extend(_render_section("New High-Fit Targets", new_items))
    lines.extend(_render_section("Follow-Ups Due", followup_items))
    return "\n".join(lines).rstrip() + "\n"


def render_email_subject(packet_date: str, new_items: list[BriefItem], followup_items: list[BriefItem]) -> str:
    return f"LeadOps Daily Brief - {packet_date} ({len(new_items)} new, {len(followup_items)} follow-ups)"


def render_email_text(
    packet_date: str,
    new_items: list[BriefItem],
    followup_items: list[BriefItem],
    *,
    approach: ApproachSpec | None = None,
) -> str:
    lines = [
        f"LeadOps Daily Brief - {packet_date}",
        "",
        f"New targets: {len(new_items)}",
        f"Follow-ups due: {len(followup_items)}",
        "",
    ]
    lines.extend(_render_email_context_text(approach))
    lines.extend(_render_email_section("New High-Fit Targets", new_items))
    lines.extend(_render_email_section("Follow-Ups Due", followup_items))
    return "\n".join(lines).rstrip() + "\n"


def render_email_html(
    packet_date: str,
    new_items: list[BriefItem],
    followup_items: list[BriefItem],
    *,
    approach: ApproachSpec | None = None,
) -> str:
    summary = (
        f'<div class="summary-card">'
        f'<div class="summary-label">Daily Brief</div>'
        f'<div class="summary-date">{escape(packet_date)}</div>'
        f'<div class="summary-stats">'
        f'<span class="pill"><strong>{len(new_items)}</strong> new</span>'
        f'<span class="pill"><strong>{len(followup_items)}</strong> due</span>'
        f"</div>"
        f"</div>"
    )
    sections = [
        _render_email_html_context(approach),
        _render_email_html_section("New High-Fit Targets", new_items, empty_message="No new targets surfaced today."),
        _render_email_html_section("Follow-Ups Due", followup_items, empty_message="No follow-ups due today."),
    ]
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8" />',
            '<meta name="viewport" content="width=device-width, initial-scale=1" />',
            f"<title>{escape(render_email_subject(packet_date, new_items, followup_items))}</title>",
            "<style>",
            "body { margin: 0; padding: 0; background: #f5f7fb; color: #162030; font: 15px/1.55 -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }",
            ".wrap { max-width: 780px; margin: 0 auto; padding: 24px 16px 40px; }",
            ".summary-card { background: linear-gradient(135deg, #162030 0%, #22314d 100%); color: #ffffff; border-radius: 16px; padding: 20px 22px; box-shadow: 0 10px 24px rgba(22, 32, 48, 0.18); }",
            ".summary-label { font-size: 12px; letter-spacing: 0.08em; text-transform: uppercase; opacity: 0.76; }",
            ".summary-date { margin-top: 4px; font-size: 28px; font-weight: 700; }",
            ".summary-stats { margin-top: 16px; display: flex; gap: 10px; flex-wrap: wrap; }",
            ".pill { display: inline-block; padding: 7px 11px; border-radius: 999px; background: rgba(255, 255, 255, 0.14); font-size: 13px; }",
            ".section { margin-top: 22px; }",
            ".section-title { margin: 0 0 10px; font-size: 18px; font-weight: 700; color: #162030; }",
            ".context-card { background: #ffffff; border: 1px solid #d9e1ec; border-radius: 14px; padding: 16px 18px; margin-top: 20px; box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06); }",
            ".context-grid { display: grid; grid-template-columns: 1fr; gap: 10px; margin-top: 10px; }",
            ".card { background: #ffffff; border: 1px solid #d9e1ec; border-radius: 14px; padding: 18px 18px 16px; margin-bottom: 14px; box-shadow: 0 6px 18px rgba(15, 23, 42, 0.06); }",
            ".card-head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: 10px; }",
            ".title { margin: 0; font-size: 17px; font-weight: 700; color: #162030; }",
            ".title a { color: inherit; text-decoration: none; }",
            ".meta { margin-top: 6px; color: #58667c; font-size: 13px; }",
            ".score { min-width: 138px; text-align: right; }",
            ".score strong { display: block; font-size: 18px; color: #162030; }",
            ".score span { display: block; font-size: 12px; color: #58667c; }",
            ".label { display: inline-block; margin-right: 6px; margin-bottom: 6px; padding: 5px 8px; border-radius: 999px; background: #eef3f8; color: #314156; font-size: 12px; }",
            ".grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 12px; }",
            ".block { background: #f7f9fc; border-radius: 10px; padding: 12px 13px; }",
            ".block-label { display: block; margin-bottom: 5px; font-size: 12px; letter-spacing: 0.05em; text-transform: uppercase; color: #66758c; }",
            ".body-copy { white-space: pre-wrap; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px; line-height: 1.5; color: #1a2435; }",
            ".list { margin: 8px 0 0; padding-left: 18px; color: #2b3b53; }",
            ".list li { margin: 4px 0; }",
            ".empty { background: #ffffff; border: 1px dashed #c7d3e3; border-radius: 14px; padding: 18px; color: #58667c; }",
            ".footer { margin-top: 18px; font-size: 12px; color: #66758c; }",
            "@media (max-width: 640px) { .card-head { display: block; } .score { text-align: left; margin-top: 8px; } }",
            "</style>",
            "</head>",
            "<body>",
            '<div class="wrap">',
            summary,
            *sections,
            '<div class="footer">LeadOps keeps this email intentionally short and only surfaces the strongest candidates for review.</div>',
            "</div>",
            "</body>",
            "</html>",
        ]
    )


def write_packet(
    packet_dir: Path,
    packet_date: str,
    new_items: list[BriefItem],
    followup_items: list[BriefItem],
    *,
    approach: ApproachSpec | None = None,
) -> tuple[Path, Path, Path, Path]:
    packet_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = packet_dir / "daily-brief.md"
    json_path = packet_dir / "daily-brief.json"
    digest_path = packet_dir / "daily-digest.txt"
    digest_html_path = packet_dir / "daily-digest.html"

    markdown = render_markdown(packet_date, new_items, followup_items, approach=approach)
    digest_text = render_email_text(packet_date, new_items, followup_items, approach=approach)
    digest_html = render_email_html(packet_date, new_items, followup_items, approach=approach)
    payload = {
        "packet_date": packet_date,
        "run_context": {
            "approach": approach.as_payload() if approach else None,
        },
        "new_targets": [_item_to_dict(item) for item in new_items],
        "followups_due": [_item_to_dict(item) for item in followup_items],
    }

    write_text(markdown_path, markdown)
    write_text(json_path, json.dumps(payload, indent=2) + "\n")
    write_text(digest_path, digest_text)
    write_text(digest_html_path, digest_html)
    return markdown_path, json_path, digest_path, digest_html_path


def _render_markdown_context(approach: ApproachSpec | None) -> list[str]:
    if not approach:
        return []
    lines = [
        "## Run Context",
        "",
        f"- Approach: `{approach.label}` (`{approach.name}`)",
        f"- Goal: {approach.strategy}",
        f"- Prioritize: {', '.join(approach.prioritize)}",
        f"- Reject: {', '.join(approach.reject)}",
        "",
    ]
    return lines


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


def _render_email_context_text(approach: ApproachSpec | None) -> list[str]:
    if not approach:
        return []
    return [
        "Run context",
        "-----------",
        f"Approach: {approach.label} ({approach.name})",
        f"Goal: {approach.strategy}",
        f"Prioritize: {', '.join(approach.prioritize)}",
        f"Reject: {', '.join(approach.reject)}",
        "",
    ]


def _render_email_html_section(title: str, items: list[BriefItem], *, empty_message: str) -> str:
    if not items:
        content = f'<div class="empty">{escape(empty_message)}</div>'
    else:
        content = "".join(_render_email_html_item(item) for item in items)
    return (
        f'<section class="section">'
        f'<h2 class="section-title">{escape(title)}</h2>'
        f"{content}"
        f"</section>"
    )


def _render_email_html_context(approach: ApproachSpec | None) -> str:
    if not approach:
        return ""
    prioritize = _render_html_list(list(approach.prioritize))
    reject = _render_html_list(list(approach.reject))
    return (
        '<section class="context-card">'
        '<h2 class="section-title">Run Context</h2>'
        f'<div class="meta"><strong>Approach:</strong> {escape(approach.label)}'
        f' <span class="label">{escape(approach.name)}</span></div>'
        f'<div class="context-grid">'
        f'<div class="block"><span class="block-label">Goal</span>{escape(approach.strategy)}</div>'
        f'<div class="block"><span class="block-label">Prioritize</span>{prioritize}</div>'
        f'<div class="block"><span class="block-label">Reject</span>{reject}</div>'
        f'</div>'
        '</section>'
    )


def _render_email_html_item(item: BriefItem) -> str:
    target = item.target
    assessment = item.assessment
    labels = "".join(
        [
            f'<span class="label">{escape(target.kind)}</span>',
            f'<span class="label">{escape(target.source)}</span>',
            f'<span class="label">rank {item.rank_index}</span>',
        ]
    )
    evidence = _render_html_list(assessment.evidence)
    risks = _render_html_list(assessment.risks)
    url = escape(target.url or "")
    title = escape(target.name)
    title_html = f'<a href="{url}">{title}</a>' if target.url else title
    return (
        '<article class="card">'
        '<div class="card-head">'
        f'<div><h3 class="title">{title_html}</h3>'
        f'<div class="meta">{labels}</div></div>'
        f'<div class="score"><strong>{assessment.fit_score:.1f}</strong>'
        f'<span>fit score</span>'
        f'<strong>{assessment.confidence:.2f}</strong>'
        f'<span>confidence</span></div>'
        '</div>'
        '<div class="grid">'
        f'<div class="block"><span class="block-label">Why fit</span>{escape(assessment.why_fit)}</div>'
        f'<div class="block"><span class="block-label">Why now</span>{escape(assessment.why_now)}</div>'
        f'<div class="block"><span class="block-label">Outreach subject</span>{escape(assessment.draft_subject)}</div>'
        f'<div class="block"><span class="block-label">Outreach angle</span>{escape(assessment.outreach_angle)}</div>'
        f'<div class="block"><span class="block-label">Draft body</span><div class="body-copy">{escape(assessment.draft_body)}</div></div>'
        f'<div class="block"><span class="block-label">Evidence</span>{evidence}</div>'
        f'<div class="block"><span class="block-label">Risks</span>{risks}</div>'
        '</div>'
        '</article>'
    )


def _render_html_list(items: list[str]) -> str:
    if not items:
        return '<div class="meta">None noted.</div>'
    return '<ul class="list">' + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"
