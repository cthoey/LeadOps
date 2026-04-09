from __future__ import annotations

from leadops.config import WorkspaceConfig
from leadops.models import AssessmentResult, RubricScores
from leadops.repository import TargetRecord


class MockProvider:
    name = "mock"

    def assess(
        self,
        target: TargetRecord,
        config: WorkspaceConfig,
        feedback_context: dict[str, list[dict[str, str]]] | None = None,
    ) -> AssessmentResult:
        text = " ".join(
            part for part in [target.name, target.notes, target.raw_evidence, target.url, target.source] if part
        ).lower()

        early_keywords = ("idea", "prototype", "beta", "waitlist", "mvp", "roadmap", "launch", "founder")
        negative_keywords = ("hire", "recruiter", "contract-to-hire", "staff aug", "fractional cto", "maintenance")
        design_keywords = ("design", "ux", "product studio", "prototype")
        team_keywords = ("small team", "tiny team", "founder-led", "cofounder", "two-person")

        work_shape_fit = 5 if any(word in text for word in early_keywords) else 2
        if target.kind == "connector" and any(word in text for word in ("design", "studio", "startup", "product")):
            work_shape_fit = max(work_shape_fit, 4)

        founder_proximity = 5 if "founder" in text or "cofounder" in text else 3
        if target.kind == "connector" and any(word in text for word in ("startup", "studio", "design")):
            founder_proximity = max(founder_proximity, 4)
        one_builder_fit = 5 if any(word in text for word in team_keywords) or target.kind == "connector" else 3
        stage_fit = 5 if any(word in text for word in ("idea", "prototype", "beta", "waitlist", "mvp")) else 3
        autonomy_fit = 4 if target.kind == "connector" or any(word in text for word in design_keywords) else 3
        product_excitement = 4 if any(word in text for word in ("startup", "launch", "prototype", "product")) else 2
        urgency_timing = 4 if any(word in text for word in ("launch", "new", "beta", "waitlist")) else 2
        evidence_strength = 4 if len(target.notes.strip()) >= 30 or target.url else 2

        staff_aug_risk = 1 if any(word in text for word in ("team extension", "staff aug")) else 0
        advisory_smell = 1 if "advis" in text or "fractional" in text else 0
        maintenance_gravity = 1 if any(word in text for word in ("maintenance", "cleanup", "rescue")) else 0
        big_team_risk = 1 if any(word in text for word in ("enterprise", "platform team", "large team")) else 0
        buyer_access_unclear = 1 if target.kind == "founder" and "founder" not in text else 0
        weak_evidence = 1 if evidence_strength < 3 else 0
        low_enjoyment = 1 if any(word in text for word in negative_keywords) else 0

        if feedback_context:
            for example in feedback_context.get("avoided", []):
                reason = f"{example.get('reason', '')} {example.get('summary', '')}".lower()
                if reason and any(token in text for token in _feedback_tokens(reason)):
                    low_enjoyment = min(5, low_enjoyment + 1)
                    weak_evidence = min(5, weak_evidence + 1)
            for example in feedback_context.get("liked", []):
                reason = f"{example.get('reason', '')} {example.get('summary', '')}".lower()
                if reason and any(token in text for token in _feedback_tokens(reason)):
                    product_excitement = min(5, product_excitement + 1)
                    founder_proximity = min(5, founder_proximity + 1)

        rubric = RubricScores(
            work_shape_fit=work_shape_fit,
            founder_proximity=founder_proximity,
            one_builder_fit=one_builder_fit,
            stage_fit=stage_fit,
            autonomy_fit=autonomy_fit,
            product_excitement=product_excitement,
            urgency_timing=urgency_timing,
            evidence_strength=evidence_strength,
            staff_aug_risk=staff_aug_risk,
            advisory_smell=advisory_smell,
            maintenance_gravity=maintenance_gravity,
            big_team_risk=big_team_risk,
            buyer_access_unclear=buyer_access_unclear,
            weak_evidence=weak_evidence,
            low_enjoyment=low_enjoyment,
        )

        recommend = rubric.gates_pass() and rubric.fit_score() >= 45
        why_fit = (
            "Signals point to early product work with plausible founder proximity and room for one accountable builder."
            if recommend
            else "The available signals are too weak or too misaligned to justify surfacing this today."
        )
        why_now = (
            "Recent or early-stage language suggests this is a better-than-average moment to reach out."
            if recommend
            else "There is not enough timing pressure or evidence to prioritize this now."
        )
        outreach_angle = (
            "Offer to help turn early product direction into a launch-ready first version."
            if target.kind == "founder"
            else "Offer to be the trusted builder after strategy or design work is complete."
        )
        draft_subject = (
            f"A builder you can keep in mind for founder-side product work"
            if target.kind == "connector"
            else f"Possible fit for early product build work at {target.name}"
        )
        draft_body = (
            f"I run a solo product engineering practice focused on helping founders and very small teams turn ideas, roadmaps, and prototypes into launch-ready customer-facing web apps.\n\n"
            f"{outreach_angle}\n\n"
            "If that seems relevant, I’d be glad to compare notes."
        )
        risks = []
        if buyer_access_unclear:
            risks.append("Direct founder access is not clearly visible from the available evidence.")
        if evidence_strength < 4:
            risks.append("Evidence is still fairly thin and may need corroboration.")

        evidence = [
            item
            for item in [
                target.notes.strip(),
                target.raw_evidence.strip(),
                target.url.strip(),
            ]
            if item
        ][:3]

        return AssessmentResult(
            recommend=recommend,
            confidence=0.75 if recommend else 0.45,
            rubric=rubric,
            why_fit=why_fit,
            why_now=why_now,
            outreach_angle=outreach_angle,
            draft_subject=draft_subject,
            draft_body=draft_body,
            risks=risks,
            evidence=evidence,
            raw_response={"provider": self.name, "mode": "heuristic"},
        )


def _feedback_tokens(text: str) -> set[str]:
    tokens = {token for token in text.split() if len(token) >= 5}
    return tokens
