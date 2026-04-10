from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RubricScores:
    work_shape_fit: int
    founder_proximity: int
    one_builder_fit: int
    stage_fit: int
    autonomy_fit: int
    product_excitement: int
    urgency_timing: int
    evidence_strength: int
    staff_aug_risk: int = 0
    advisory_smell: int = 0
    maintenance_gravity: int = 0
    big_team_risk: int = 0
    buyer_access_unclear: int = 0
    weak_evidence: int = 0
    low_enjoyment: int = 0

    def fit_score(self) -> float:
        positive = (
            self.work_shape_fit * 4
            + self.founder_proximity * 4
            + self.one_builder_fit * 4
            + self.stage_fit * 3
            + self.autonomy_fit * 3
            + self.product_excitement * 2
            + self.urgency_timing * 2
            + self.evidence_strength * 3
        )
        negative = (
            self.staff_aug_risk * 5
            + self.advisory_smell * 4
            + self.maintenance_gravity * 4
            + self.big_team_risk * 3
            + self.buyer_access_unclear * 3
            + self.weak_evidence * 3
            + self.low_enjoyment * 4
        )
        return float(positive - negative)

    def gates_pass(self, *, kind: str | None = None) -> bool:
        base_pass = (
            self.work_shape_fit >= 4
            and self.founder_proximity >= 4
            and self.one_builder_fit >= 4
            and self.evidence_strength >= 3
        )
        if not base_pass:
            return False
        if kind == "founder":
            return self.stage_fit >= 4 and self.urgency_timing >= 3
        return True

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AssessmentResult:
    recommend: bool
    confidence: float
    rubric: RubricScores
    why_fit: str
    why_now: str
    outreach_angle: str
    draft_subject: str
    draft_body: str
    risks: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)

    @property
    def fit_score(self) -> float:
        return self.rubric.fit_score()

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["fit_score"] = self.fit_score
        return payload


def assessment_from_dict(data: dict[str, Any]) -> AssessmentResult:
    rubric = RubricScores(**data["rubric"])
    return AssessmentResult(
        recommend=bool(data["recommend"]),
        confidence=float(data["confidence"]),
        rubric=rubric,
        why_fit=str(data["why_fit"]),
        why_now=str(data["why_now"]),
        outreach_angle=str(data["outreach_angle"]),
        draft_subject=str(data["draft_subject"]),
        draft_body=str(data["draft_body"]),
        risks=[str(item) for item in data.get("risks", [])],
        evidence=[str(item) for item in data.get("evidence", [])],
        raw_response=dict(data.get("raw_response", {})),
    )


@dataclass(slots=True)
class DiscoveryCandidate:
    name: str
    url: str
    confidence: float
    fit_score: float
    why_fit: str
    why_now: str
    evidence: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)

    def notes_text(self) -> str:
        parts = [item for item in [self.why_fit.strip(), self.why_now.strip()] if item]
        return "\n\n".join(parts)

    def raw_evidence_text(self) -> str:
        sections: list[str] = []
        if self.evidence:
            sections.append("Evidence:\n" + "\n".join(f"- {item}" for item in self.evidence))
        if self.source_urls:
            sections.append("Sources:\n" + "\n".join(f"- {item}" for item in self.source_urls))
        if self.risks:
            sections.append("Risks:\n" + "\n".join(f"- {item}" for item in self.risks))
        return "\n\n".join(sections)

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
            fit_score=float(item["fit_score"]),
            why_fit=str(item["why_fit"]).strip(),
            why_now=str(item["why_now"]).strip(),
            evidence=[str(entry).strip() for entry in item.get("evidence", []) if str(entry).strip()],
            source_urls=[str(entry).strip() for entry in item.get("source_urls", []) if str(entry).strip()],
            risks=[str(entry).strip() for entry in item.get("risks", []) if str(entry).strip()],
        )
        if not candidate.name or not candidate.url:
            continue
        candidates.append(candidate)
    return DiscoveryBatch(
        candidates=candidates,
        raw_response=dict(data.get("raw_response", {})),
    )
