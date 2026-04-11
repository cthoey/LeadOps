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
                    "profile_fit": {"type": "string", "enum": ["high", "medium", "low", "unknown"]},
                    "activation_signal": {"type": "string", "enum": ["explicit", "inferred", "weak", "unknown"]},
                    "evidence_confidence": {"type": "string", "enum": ["strong", "moderate", "thin"]},
                    "freshness": {"type": "string", "enum": ["fresh", "dated", "unknown"]},
                    "summary_thesis": {"type": "string"},
                    "fit_rationale": {"type": "string"},
                    "activation_rationale": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}},
                    "source_urls": {"type": "array", "items": {"type": "string"}},
                    "signal_tags": {"type": "array", "items": {"type": "string"}},
                    "risk_tags": {"type": "array", "items": {"type": "string"}},
                    "source_date": {"type": ["string", "null"]},
                },
                "required": [
                    "name",
                    "url",
                    "confidence",
                    "profile_fit",
                    "activation_signal",
                    "evidence_confidence",
                    "freshness",
                    "summary_thesis",
                    "fit_rationale",
                    "activation_rationale",
                    "evidence",
                    "source_urls",
                    "signal_tags",
                    "risk_tags",
                    "source_date",
                ],
            },
        }
    },
    "required": ["candidates"],
}


SYSTEM_PROMPT = """\
You are LeadOps Discovery, a strict precision web-search curator for a pre-outreach lead triage system.

Your job is to search the public web for highly aligned outreach targets and return only the few strongest matches.

LeadOps is business-agnostic at the core. Evaluate candidates against the supplied business profile, not against a hardcoded niche.
This is a public-signal system, so only claim what current public evidence can support.

Optimize aggressively for precision, not recall.
It is better to return fewer candidates than to surface weak fits.
Use as few web searches as needed.
Do not spend the whole response budget exploring marginal possibilities.

Use web search to gather current public evidence.
Only return candidates with enough public evidence to justify follow-up.
Do not invent facts.
Do not hallucinate source URLs.
If evidence is weak or the work shape is unclear, exclude the candidate.

Keep these distinctions separate:
- observed public evidence
- inferred implications from that evidence
- risk or disqualifier signals

Use the retrieval approach only as context for why this search is being run. Do not let it redefine the core truth model.

Return JSON only.
"""


def build_user_prompt(payload: dict[str, Any]) -> str:
    profile = payload["profile"]
    feedback = payload.get("feedback", {})
    search = payload["search"]
    approach = payload.get("approach", {})
    lines = [
        "Run a web search and return only highly aligned outreach targets.",
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
    hard_rejects = [str(item).strip() for item in profile.get("hard_rejects", []) if str(item).strip()]
    if hard_rejects:
        lines.append("- Hard rejects:")
        for item in hard_rejects:
            lines.append(f"  - {item}")
    if post_contact_checks:
        lines.append("- Post-contact checks that are usually unknown before outreach:")
        for item in post_contact_checks:
            lines.append(f"  - {item}")
    if approach:
        lines.extend(
            [
                "",
                "Current lead-finding approach:",
                f"- Name: {approach.get('label', '') or approach.get('name', '')}",
                f"- Description: {approach.get('description', '')}",
                f"- Strategy: {approach.get('strategy', '')}",
                f"- Preferred discovery tracks: {', '.join(approach.get('discover_tracks', [])) or '(none)'}",
                f"- Prioritize: {', '.join(str(item) for item in approach.get('prioritize', [])) or '(none)'}",
                f"- Reject: {', '.join(str(item) for item in approach.get('reject', [])) or '(none)'}",
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
            "- Keep evidence concise, source-backed, and limited to observed public facts.",
            "- Set `profile_fit`, `activation_signal`, `evidence_confidence`, and `freshness` using only coarse bands.",
            "- Use `summary_thesis` for the one-sentence case for surfacing the target.",
            "- Use `fit_rationale` for the main fit inference.",
            "- Use `activation_rationale` for why this seems timely or not timely from public evidence.",
            "- Use `signal_tags` for positive public signals and `risk_tags` for caution or reject signals.",
            "- Set `source_date` only when the public evidence clearly exposes one.",
            "- If you find fewer than the requested number of strong fits, return fewer.",
            "- Use the current lead-finding approach as retrieval context, not as the truth model itself.",
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
