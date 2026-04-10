from __future__ import annotations

import json
from typing import Any


ASSESSMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "recommend": {"type": "boolean"},
        "confidence": {"type": "number"},
        "rubric": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "work_shape_fit": {"type": "integer", "minimum": 0, "maximum": 5},
                "founder_proximity": {"type": "integer", "minimum": 0, "maximum": 5},
                "one_builder_fit": {"type": "integer", "minimum": 0, "maximum": 5},
                "stage_fit": {"type": "integer", "minimum": 0, "maximum": 5},
                "autonomy_fit": {"type": "integer", "minimum": 0, "maximum": 5},
                "product_excitement": {"type": "integer", "minimum": 0, "maximum": 5},
                "urgency_timing": {"type": "integer", "minimum": 0, "maximum": 5},
                "evidence_strength": {"type": "integer", "minimum": 0, "maximum": 5},
                "staff_aug_risk": {"type": "integer", "minimum": 0, "maximum": 5},
                "advisory_smell": {"type": "integer", "minimum": 0, "maximum": 5},
                "maintenance_gravity": {"type": "integer", "minimum": 0, "maximum": 5},
                "big_team_risk": {"type": "integer", "minimum": 0, "maximum": 5},
                "buyer_access_unclear": {"type": "integer", "minimum": 0, "maximum": 5},
                "weak_evidence": {"type": "integer", "minimum": 0, "maximum": 5},
                "low_enjoyment": {"type": "integer", "minimum": 0, "maximum": 5},
            },
            "required": [
                "work_shape_fit",
                "founder_proximity",
                "one_builder_fit",
                "stage_fit",
                "autonomy_fit",
                "product_excitement",
                "urgency_timing",
                "evidence_strength",
                "staff_aug_risk",
                "advisory_smell",
                "maintenance_gravity",
                "big_team_risk",
                "buyer_access_unclear",
                "weak_evidence",
                "low_enjoyment",
            ],
        },
        "why_fit": {"type": "string"},
        "why_now": {"type": "string"},
        "outreach_angle": {"type": "string"},
        "draft_subject": {"type": "string"},
        "draft_body": {"type": "string"},
        "risks": {"type": "array", "items": {"type": "string"}},
        "evidence": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "recommend",
        "confidence",
        "rubric",
        "why_fit",
        "why_now",
        "outreach_angle",
        "draft_subject",
        "draft_body",
        "risks",
        "evidence",
    ],
}


SYSTEM_PROMPT = """\
You are LeadOps, a strict precision lead curator for a solo independent product engineer.

The consulting business you are judging for is extremely specific:
- founder-side and startup-side
- helping founders or very small teams turn real product ideas, roadmaps, and prototypes into launch-ready customer-facing web apps
- direct founder collaboration
- one accountable builder

The business explicitly does NOT want:
- staff augmentation
- employment-style work
- recruiter funnels
- fractional CTO or advisory-only work
- rescue, cleanup, or maintenance as the main lane
- mature companies with established engineering orgs

Your job is to decide whether this target is precise enough and attractive enough to surface in a tiny daily review packet.

Optimize for precision, not recall.
It is better to reject a maybe-fit than to surface a weak lead.

Use only the provided evidence. Do not invent facts.
If evidence is weak, say so in the scoring and risks.
If direct founder access is unclear, penalize it.
If the work smells like staff augmentation, hiring, maintenance, or advisory work, penalize it heavily.
Only reward founder targets when public evidence suggests paying one external builder is a real next step.
Do not reward an existing product unless the evidence shows a real implementation gap, design-to-build handoff, roadmap pressure, or no obvious engineering team.
Connector targets are valid only when they plausibly lead to roadmap-to-build or prototype-to-launch work.

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
    hard_rejects = profile.get("hard_rejects", [])
    if hard_rejects:
        lines.append("- Hard rejects:")
        for item in hard_rejects:
            lines.append(f"  - {item}")
    if approach:
        lines.extend(
            [
                "- Current lead-finding approach:",
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
            "Score the target using the rubric dimensions in the schema.",
            "Use integer scores from 0 to 5 for every rubric field.",
            "Only recommend the target if it looks like a strong fit you would genuinely want in a tiny daily review packet.",
            "For founder targets, only recommend when the evidence suggests one accountable external builder is a plausible next step now.",
            "Apply the current lead-finding approach when deciding what to reward or reject.",
            "Keep rationale concise and evidence-backed.",
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
