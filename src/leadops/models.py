from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PROFILE_FIT_RANK = {
    "high": 3,
    "medium": 2,
    "low": 1,
    "unknown": 0,
}

ACTIVATION_SIGNAL_RANK = {
    "explicit": 3,
    "inferred": 2,
    "weak": 1,
    "unknown": 0,
}

EVIDENCE_CONFIDENCE_RANK = {
    "strong": 3,
    "moderate": 2,
    "thin": 1,
}

FRESHNESS_RANK = {
    "fresh": 3,
    "dated": 2,
    "unknown": 1,
}

ACTION_QUEUE_ORDER = {
    "pursue_now": 0,
    "watch": 1,
    "nurture": 2,
    "decline": 3,
    "followup_due": 0,
}

VISIBLE_CANDIDATE_QUEUES = {"pursue_now", "watch", "nurture"}
ACTIONABLE_QUEUES = {"pursue_now", "followup_due"}


@dataclass(slots=True)
class AssessmentResult:
    confidence: float
    profile_fit: str
    activation_signal: str
    evidence_confidence: str
    freshness: str
    action_queue: str
    summary_thesis: str
    fit_rationale: str
    activation_rationale: str
    outreach_angle: str = ""
    draft_subject: str = ""
    draft_body: str = ""
    signal_tags: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    unknowns_to_verify: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)
    source_date: str | None = None

    @property
    def recommend(self) -> bool:
        return self.action_queue != "decline"

    @property
    def priority_score(self) -> float:
        return _coarse_priority_score(
            profile_fit=self.profile_fit,
            activation_signal=self.activation_signal,
            evidence_confidence=self.evidence_confidence,
            freshness=self.freshness,
            confidence=self.confidence,
            risk_count=len(self.risk_tags),
        )

    @property
    def is_outreach_ready(self) -> bool:
        return self.action_queue in ACTIONABLE_QUEUES and bool(
            self.outreach_angle.strip() or self.draft_subject.strip() or self.draft_body.strip()
        )

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["recommend"] = self.recommend
        payload["priority_score"] = self.priority_score
        return payload


def assessment_from_dict(data: dict[str, Any]) -> AssessmentResult:
    action_queue = _normalize_queue(str(data.get("action_queue", "watch")))
    return AssessmentResult(
        confidence=float(data["confidence"]),
        profile_fit=_normalize_choice(str(data.get("profile_fit", "unknown")), PROFILE_FIT_RANK, default="unknown"),
        activation_signal=_normalize_choice(
            str(data.get("activation_signal", "unknown")),
            ACTIVATION_SIGNAL_RANK,
            default="unknown",
        ),
        evidence_confidence=_normalize_choice(
            str(data.get("evidence_confidence", "thin")),
            EVIDENCE_CONFIDENCE_RANK,
            default="thin",
        ),
        freshness=_normalize_choice(str(data.get("freshness", "unknown")), FRESHNESS_RANK, default="unknown"),
        action_queue=action_queue,
        summary_thesis=str(data.get("summary_thesis", "")).strip() or str(data.get("fit_rationale", "")).strip(),
        fit_rationale=str(data.get("fit_rationale", "")).strip(),
        activation_rationale=str(data.get("activation_rationale", "")).strip(),
        outreach_angle=str(data.get("outreach_angle", "")),
        draft_subject=str(data.get("draft_subject", "")),
        draft_body=str(data.get("draft_body", "")),
        signal_tags=[str(item).strip() for item in data.get("signal_tags", []) if str(item).strip()],
        risk_tags=[str(item).strip() for item in data.get("risk_tags", []) if str(item).strip()],
        unknowns_to_verify=[
            str(item).strip() for item in data.get("unknowns_to_verify", []) if str(item).strip()
        ],
        evidence=[str(item).strip() for item in data.get("evidence", []) if str(item).strip()],
        raw_response=dict(data.get("raw_response", {})),
        source_date=_normalize_source_date(data.get("source_date")),
    )


@dataclass(slots=True)
class DiscoveryCandidate:
    name: str
    url: str
    confidence: float
    profile_fit: str
    activation_signal: str
    evidence_confidence: str
    freshness: str
    summary_thesis: str
    fit_rationale: str
    activation_rationale: str
    evidence: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    signal_tags: list[str] = field(default_factory=list)
    risk_tags: list[str] = field(default_factory=list)
    source_date: str | None = None

    def notes_text(self) -> str:
        parts = [
            item
            for item in [
                self.summary_thesis.strip(),
                self.fit_rationale.strip(),
                self.activation_rationale.strip(),
            ]
            if item
        ]
        return "\n\n".join(parts)

    def raw_evidence_text(self) -> str:
        sections: list[str] = []
        if self.evidence:
            sections.append("Evidence:\n" + "\n".join(f"- {item}" for item in self.evidence))
        if self.source_urls:
            sections.append("Sources:\n" + "\n".join(f"- {item}" for item in self.source_urls))
        if self.signal_tags:
            sections.append("Signals:\n" + "\n".join(f"- {item}" for item in self.signal_tags))
        if self.risk_tags:
            sections.append("Risks:\n" + "\n".join(f"- {item}" for item in self.risk_tags))
        if self.source_date:
            sections.append(f"Source date:\n- {self.source_date}")
        return "\n\n".join(sections)

    @property
    def priority_score(self) -> float:
        return _coarse_priority_score(
            profile_fit=self.profile_fit,
            activation_signal=self.activation_signal,
            evidence_confidence=self.evidence_confidence,
            freshness=self.freshness,
            confidence=self.confidence,
            risk_count=len(self.risk_tags),
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DiscoveryBatch:
    candidates: list[DiscoveryCandidate]
    raw_response: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidates": [candidate.as_dict() for candidate in self.candidates],
            "raw_response": self.raw_response,
        }


def discovery_batch_from_dict(data: dict[str, Any]) -> DiscoveryBatch:
    candidates: list[DiscoveryCandidate] = []
    for item in data.get("candidates", []):
        candidate = DiscoveryCandidate(
            name=str(item["name"]).strip(),
            url=str(item["url"]).strip(),
            confidence=float(item["confidence"]),
            profile_fit=_normalize_choice(str(item.get("profile_fit", "unknown")), PROFILE_FIT_RANK, default="unknown"),
            activation_signal=_normalize_choice(
                str(item.get("activation_signal", "unknown")),
                ACTIVATION_SIGNAL_RANK,
                default="unknown",
            ),
            evidence_confidence=_normalize_choice(
                str(item.get("evidence_confidence", "thin")),
                EVIDENCE_CONFIDENCE_RANK,
                default="thin",
            ),
            freshness=_normalize_choice(str(item.get("freshness", "unknown")), FRESHNESS_RANK, default="unknown"),
            summary_thesis=str(item.get("summary_thesis", "")).strip(),
            fit_rationale=str(item.get("fit_rationale", "")).strip(),
            activation_rationale=str(item.get("activation_rationale", "")).strip(),
            evidence=[str(entry).strip() for entry in item.get("evidence", []) if str(entry).strip()],
            source_urls=[str(entry).strip() for entry in item.get("source_urls", []) if str(entry).strip()],
            signal_tags=[str(entry).strip() for entry in item.get("signal_tags", []) if str(entry).strip()],
            risk_tags=[str(entry).strip() for entry in item.get("risk_tags", []) if str(entry).strip()],
            source_date=_normalize_source_date(item.get("source_date")),
        )
        if not candidate.name or not candidate.url:
            continue
        candidates.append(candidate)
    return DiscoveryBatch(
        candidates=candidates,
        raw_response=dict(data.get("raw_response", {})),
    )


def _normalize_choice(value: str, allowed: dict[str, int], *, default: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in allowed else default


def _normalize_queue(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return normalized if normalized in ACTION_QUEUE_ORDER else "watch"


def _normalize_source_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _coarse_priority_score(
    *,
    profile_fit: str,
    activation_signal: str,
    evidence_confidence: str,
    freshness: str,
    confidence: float,
    risk_count: int,
) -> float:
    score = 0.0
    score += PROFILE_FIT_RANK.get(profile_fit, 0) * 40
    score += ACTIVATION_SIGNAL_RANK.get(activation_signal, 0) * 25
    score += EVIDENCE_CONFIDENCE_RANK.get(evidence_confidence, 0) * 15
    score += FRESHNESS_RANK.get(freshness, 0) * 8
    score += max(0.0, min(confidence, 1.0)) * 10
    score -= min(risk_count, 5) * 4
    return score
