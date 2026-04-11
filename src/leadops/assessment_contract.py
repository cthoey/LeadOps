from __future__ import annotations

import json
from typing import Any


ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "confidence": {"type": "number"},
        "profile_fit": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
        "activation_signal": {"type": "string", "enum": ["explicit", "inferred", "weak", "unknown"]},
        "evidence_confidence": {"type": "string", "enum": ["strong", "moderate", "thin"]},
        "freshness": {"type": "string", "enum": ["fresh", "dated", "unknown"]},
        "action_queue": {"type": "string", "enum": ["pursue_now", "watch", "nurture", "decline"]},
        "summary_thesis": {"type": "string"},
        "fit_rationale": {"type": "string"},
        "activation_rationale": {"type": "string"},
        "outreach_angle": {"type": "string"},
        "draft_subject": {"type": "string"},
        "draft_body": {"type": "string"},
        "signal_tags": {"type": "array", "items": {"type": "string"}},
        "risk_tags": {"type": "array", "items": {"type": "string"}},
        "unknowns_to_verify": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
        "source_date": {"type": ["string", "null"]},
    },
    "required": [
        "confidence",
        "profile_fit",
        "activation_signal",
        "evidence_confidence",
        "freshness",
        "action_queue",
        "summary_thesis",
        "fit_rationale",
        "activation_rationale",
        "outreach_angle",
        "draft_subject",
        "draft_body",
        "signal_tags",
        "risk_tags",
        "unknowns_to_verify",
        "evidence",
        "source_date",
    ],
}


SYSTEM_PROMPT = """\
You are LeadOps, a strict pre-outreach lead triage assistant.

Evaluate targets against the supplied business profile, not against any hardcoded niche.
This is a public-signal system. It should only claim what current public evidence can support.

Your job is to decide:
- how well the target matches the business profile
- whether public evidence suggests a reason to reach out now
- how strong the evidence is
- how fresh the signal appears
- what action queue the target belongs in

Keep these distinctions separate:
- observed public evidence
- inferred implications from that evidence
- unknowns that must be verified after contact

Do not invent facts.
Do not assume budget, authority, sponsor quality, internal ownership, or delivery viability unless explicitly supported.
If evidence is weak, say so.
If the target clearly violates hard rejects or looks like a poor fit, decline it.
Use the retrieval approach only as context for why this target surfaced. Do not let it redefine the core truth model.

Return JSON only.
"""


def build_user_prompt(payload: dict[str, Any]) -> str:
    profile = payload["profile"]
    feedback = payload.get("feedback", {})
    target = payload["target"]
    approach = payload.get("approach", {})
    lines = [
        "Assess this target for fit with the consulting business.",
        "",
        "Business profile:",
        f"- Name: {profile.get('name', '')}",
        f"- Offer: {profile.get('offer', '')}",
    ]
    ideal_customer = str(profile.get("ideal_customer", "")).strip()
    fit_definition = str(profile.get("fit_definition", "")).strip()
    preferred_signals = [str(item).strip() for item in profile.get("preferred_signals", []) if str(item).strip()]
    caution_signals = [str(item).strip() for item in profile.get("caution_signals", []) if str(item).strip()]
    post_contact_checks = [str(item).strip() for item in profile.get("post_contact_checks", []) if str(item).strip()]
    if ideal_customer:
        lines.append(f"- Ideal customer: {ideal_customer}")
    if fit_definition:
        lines.append(f"- Fit definition: {fit_definition}")
    if preferred_signals:
        lines.append("- Preferred public-fit signals:")
        for item in preferred_signals:
            lines.append(f"  - {item}")
    if caution_signals:
        lines.append("- Caution signals:")
        for item in caution_signals:
            lines.append(f"  - {item}")
    hard_rejects = profile.get("hard_rejects", [])
    if hard_rejects:
        lines.append("- Hard rejects:")
        for item in hard_rejects:
            lines.append(f"  - {item}")
    if post_contact_checks:
        lines.append("- Post-contact checks to leave as unknown unless evidence is explicit:")
        for item in post_contact_checks:
            lines.append(f"  - {item}")
    if approach:
        lines.extend(
            [
                "- Current lead-finding approach (retrieval context only):",
                f"  - Name: {approach.get('label', '') or approach.get('name', '')}",
                f"  - Description: {approach.get('description', '')}",
                f"  - Strategy: {approach.get('strategy', '')}",
                f"  - Prioritize: {', '.join(str(item) for item in approach.get('prioritize', [])) or '(none)'}",
                f"  - Reject: {', '.join(str(item) for item in approach.get('reject', [])) or '(none)'}",
            ]
        )
    liked = feedback.get("liked", [])
    avoided = feedback.get("avoided", [])
    if liked or avoided:
        lines.extend(["", "Recent operator feedback:"])
        if liked:
            lines.append("- Previously liked or advanced patterns:")
            for item in liked:
                summary = item.get("summary", "")
                reason = item.get("reason", "")
                lines.append(
                    f"  - [{item.get('action', '')}] {item.get('name', '')}: "
                    f"{reason or summary or '(no rationale recorded)'}"
                )
        if avoided:
            lines.append("- Previously rejected or avoided patterns:")
            for item in avoided:
                summary = item.get("summary", "")
                reason = item.get("reason", "")
                lines.append(
                    f"  - [{item.get('action', '')}] {item.get('name', '')}: "
                    f"{reason or summary or '(no rationale recorded)'}"
                )
    lines.extend(
        [
            "",
            "Target:",
            f"- Kind: {target.get('kind', '')}",
            f"- Name: {target.get('name', '')}",
            f"- URL: {target.get('url', '')}",
            f"- Source: {target.get('source', '')}",
            "- Notes:",
            target.get("notes", "") or "(none)",
            "- Raw evidence:",
            target.get("raw_evidence", "") or "(none)",
            "",
            "Return the schema fields exactly.",
            "Use only coarse bands and tags, not hidden numeric scoring.",
            "Choose `profile_fit` based on alignment with the supplied offer and hard rejects.",
            "Choose `activation_signal` based on public evidence of a visible ask, timing trigger, or implementation gap.",
            "Choose `evidence_confidence` based on how concrete and source-backed the evidence is.",
            "Choose `freshness` only when the source appears time-sensitive or dated. Otherwise use `unknown`.",
            "Choose `action_queue` as one of: pursue_now, watch, nurture, decline.",
            "Keep `summary_thesis` to one sentence.",
            "Use `fit_rationale` for the main inference about fit.",
            "Use `activation_rationale` for why this should or should not be acted on now.",
            "Put only observed facts in `evidence`.",
            "Put post-contact questions in `unknowns_to_verify`.",
            "Leave `outreach_angle`, `draft_subject`, and `draft_body` empty unless `action_queue` is `pursue_now`.",
        ]
    )
    return "\n".join(lines)


def provider_payload(target_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(target_payload)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "leadops_assessment",
                "schema": ASSESSMENT_SCHEMA,
                "strict": True,
            }
        },
    }


def extract_output_text(response_payload: dict[str, Any]) -> str:
    top_level_text = response_payload.get("output_text")
    if isinstance(top_level_text, str) and top_level_text.strip():
        return top_level_text

    output = response_payload.get("output", [])
    seen_types: list[str] = []
    for item in output:
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            seen_types.append(str(content.get("type", "unknown")))
            if content.get("type") == "output_text":
                text = str(content.get("text", ""))
                if text.strip():
                    return text
            if "text" in content and isinstance(content.get("text"), str):
                text = str(content.get("text", ""))
                if text.strip():
                    return text
    raise ValueError(f"Could not find output text in response payload. Seen content types: {seen_types}")


def compact_response_metadata(response_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": response_payload.get("id"),
        "model": response_payload.get("model"),
        "status": response_payload.get("status"),
        "usage": response_payload.get("usage"),
    }


def pretty_schema() -> str:
    return json.dumps(ASSESSMENT_SCHEMA, indent=2) + "\n"
