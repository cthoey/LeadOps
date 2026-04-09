from __future__ import annotations

from typing import Any


DISCOVERY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "url": {"type": "string"},
                    "confidence": {"type": "number"},
                    "fit_score": {"type": "number"},
                    "why_fit": {"type": "string"},
                    "why_now": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "source_urls": {"type": "array", "items": {"type": "string"}},
                    "risks": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "name",
                    "url",
                    "confidence",
                    "fit_score",
                    "why_fit",
                    "why_now",
                    "evidence",
                    "source_urls",
                    "risks",
                ],
            },
        }
    },
    "required": ["candidates"],
}


SYSTEM_PROMPT = """\
You are LeadOps Discovery, a strict precision web-search curator for a solo independent product engineer.

Your job is to search the public web for highly aligned outreach targets and return only the few strongest matches.

The consulting business is extremely specific:
- founder-side and startup-side
- helping founders or very small teams turn ideas, roadmaps, and rough prototypes into launch-ready customer-facing web apps
- direct founder collaboration
- one accountable builder

The business explicitly does NOT want:
- staff augmentation
- employment-style work
- recruiter funnels
- fractional CTO or advisory-only work
- rescue, cleanup, or maintenance as the main lane
- mature companies with established engineering orgs

Optimize aggressively for precision, not recall.
It is better to return fewer candidates than to surface weak fits.
Use as few web searches as needed.
Do not spend the whole response budget exploring marginal possibilities.

Use web search to gather current public evidence.
Only return candidates with enough public evidence to justify follow-up.
Do not invent facts.
Do not hallucinate source URLs.
If evidence is weak or the work shape is unclear, exclude the candidate.

Return JSON only.
"""


def build_user_prompt(payload: dict[str, Any]) -> str:
    profile = payload["profile"]
    feedback = payload.get("feedback", {})
    search = payload["search"]
    lines = [
        "Run a web search and return only highly aligned outreach targets.",
        "",
        "Business profile:",
        f"- Name: {profile.get('name', '')}",
        f"- Offer: {profile.get('offer', '')}",
        "- Hard rejects:",
    ]
    for item in profile.get("hard_rejects", []):
        lines.append(f"  - {item}")
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
            "Search request:",
            f"- Kind: {search.get('kind', '')}",
            f"- Query: {search.get('query', '')}",
            f"- Maximum candidates: {search.get('limit', 5)}",
            "",
            "Instructions:",
            "- Search the web for current public evidence.",
            "- Use a tight search budget and stop once you have enough evidence.",
            "- Return at most the requested number of candidates.",
            "- Prefer official company/founder pages when possible.",
            "- Only include candidates you would genuinely want in a tiny daily review packet.",
            "- Keep evidence concise and source-backed.",
            "- If you find fewer than the requested number of strong fits, return fewer.",
        ]
    )
    return "\n".join(lines)


def provider_payload(search_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(search_payload)},
        ],
        "tools": [{"type": "web_search"}],
        "tool_choice": "auto",
        "include": ["web_search_call.action.sources"],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "leadops_discovery",
                "schema": DISCOVERY_SCHEMA,
                "strict": True,
            }
        },
    }
