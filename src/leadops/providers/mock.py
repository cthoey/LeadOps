from __future__ import annotations

from leadops.approaches import ApproachSpec
from leadops.config import WorkspaceConfig
from leadops.models import AssessmentResult
from leadops.repository import TargetRecord


class MockProvider:
    name = "mock"

    def assess(
        self,
        target: TargetRecord,
        config: WorkspaceConfig,
        approach: ApproachSpec | None = None,
        feedback_context: dict[str, list[dict[str, str]]] | None = None,
    ) -> AssessmentResult:
        text = " ".join(
            part for part in [target.name, target.notes, target.raw_evidence, target.url, target.source] if part
        ).lower()

        early_keywords = ("idea", "prototype", "mvp", "roadmap", "wireframe", "launch", "founder")
        negative_keywords = ("hire", "recruiter", "contract-to-hire", "staff aug", "fractional cto", "maintenance")
        explicit_ask_keywords = (
            "looking for",
            "need help",
            "need a developer",
            "build help",
            "build partner",
            "project-based",
            "milestone-based",
            "seeking freelancer",
            "implementation help",
        )
        design_keywords = ("design", "ux", "product studio", "prototype", "wireframe", "handoff")
        team_keywords = ("small team", "tiny team", "founder-led", "cofounder", "two-person")
        transition_keywords = (
            "no-code",
            "nocode",
            "prototype",
            "roadmap",
            "wireframe",
            "v1",
            "v1.1",
            "handoff",
            "build help",
            "engineering help",
            "build partner",
            "project-based",
            "milestone-based",
            "work directly with",
            "no engineering team",
            "custom build",
            "launch-ready",
        )
        live_product_keywords = ("launched", "live product", "customers", "production", "active users", "in market")

        work_shape_fit = 5 if any(word in text for word in early_keywords) else 2
        if target.kind == "connector" and any(word in text for word in ("design", "studio", "startup", "product")):
            work_shape_fit = max(work_shape_fit, 4)

        decision_access_signal = 5 if "founder" in text or "cofounder" in text else 3
        if target.kind == "connector" and any(word in text for word in ("startup", "studio", "design")):
            decision_access_signal = max(decision_access_signal, 4)
        builder_gap_signal = 5 if any(word in text for word in team_keywords) or target.kind == "connector" else 3
        stage_signal = 5 if any(word in text for word in ("idea", "prototype", "mvp", "roadmap", "wireframe")) else 3
        scope_freedom_signal = 4 if target.kind == "connector" or any(word in text for word in design_keywords) else 3
        positive_interest_signal = 4 if any(word in text for word in ("startup", "launch", "prototype", "product")) else 2
        activation_strength = 4 if any(word in text for word in ("launch", "new", "prototype", "roadmap", "build help")) else 2
        evidence_strength = 4 if len(target.notes.strip()) >= 30 or target.url else 2

        staff_aug_risk = 1 if any(word in text for word in ("team extension", "staff aug")) else 0
        advisory_risk = 1 if "advis" in text or "fractional" in text else 0
        maintenance_risk = 1 if any(word in text for word in ("maintenance", "cleanup", "rescue")) else 0
        mature_org_risk = 1 if any(word in text for word in ("enterprise", "platform team", "large team")) else 0
        decision_access_unclear = 1 if target.kind == "founder" and "founder" not in text else 0
        thin_evidence_risk = 1 if evidence_strength < 3 else 0
        negative_fit_signal = 1 if any(word in text for word in negative_keywords) else 0

        has_gap_signal = any(word in text for word in transition_keywords)
        has_live_signal = any(word in text for word in live_product_keywords)
        has_explicit_ask = any(word in text for word in explicit_ask_keywords)
        if target.kind == "founder":
            if has_gap_signal:
                work_shape_fit = min(5, work_shape_fit + 1)
                builder_gap_signal = min(5, builder_gap_signal + 2)
                activation_strength = min(5, activation_strength + 1)
                stage_signal = min(5, stage_signal + 1)
            if has_live_signal and not has_gap_signal:
                work_shape_fit = max(0, work_shape_fit - 2)
                builder_gap_signal = max(0, builder_gap_signal - 3)
                stage_signal = max(0, stage_signal - 1)
                activation_strength = max(0, activation_strength - 1)
                decision_access_unclear = min(5, decision_access_unclear + 1)
                negative_fit_signal = min(5, negative_fit_signal + 1)

        approach_name = approach.name if approach else ""
        if approach_name == "transition_focus":
            if target.kind == "founder":
                if not has_gap_signal:
                    work_shape_fit = max(0, work_shape_fit - 1)
                    builder_gap_signal = max(0, builder_gap_signal - 1)
            else:
                positive_interest_signal = max(2, positive_interest_signal - 1)
        elif approach_name == "public_signal_watch":
            if any(word in text for word in ("cofounder", "equity", "technical cofounder")):
                advisory_risk = min(5, advisory_risk + 2)
                negative_fit_signal = min(5, negative_fit_signal + 2)
            if any(word in text for word in ("freelancer", "seeking freelancer", "looking for developer", "project-based", "milestone-based")):
                activation_strength = min(5, activation_strength + 1)
                evidence_strength = min(5, evidence_strength + 1)

        if feedback_context:
            for example in feedback_context.get("avoided", []):
                reason = f"{example.get('reason', '')} {example.get('summary', '')}".lower()
                if reason and any(token in text for token in _feedback_tokens(reason)):
                    negative_fit_signal = min(5, negative_fit_signal + 1)
                    thin_evidence_risk = min(5, thin_evidence_risk + 1)
            for example in feedback_context.get("liked", []):
                reason = f"{example.get('reason', '')} {example.get('summary', '')}".lower()
                if reason and any(token in text for token in _feedback_tokens(reason)):
                    positive_interest_signal = min(5, positive_interest_signal + 1)
                    decision_access_signal = min(5, decision_access_signal + 1)

        profile_fit = (
            "high"
            if work_shape_fit >= 4 and builder_gap_signal >= 4 and negative_fit_signal <= 1
            else "medium"
            if work_shape_fit >= 3 and negative_fit_signal <= 2
            else "low"
        )
        if mature_org_risk >= 3 or maintenance_risk >= 3:
            profile_fit = "low"

        activation_signal = (
            "explicit"
            if has_explicit_ask
            else "inferred"
            if activation_strength >= 4 or has_gap_signal
            else "weak"
        )
        evidence_confidence = "strong" if evidence_strength >= 4 else "moderate" if evidence_strength >= 3 else "thin"
        freshness = (
            "fresh"
            if any(word in text for word in ("today", "this week", "now", "urgent", "launching soon"))
            else "unknown"
        )

        signal_tags: list[str] = []
        if has_explicit_ask:
            signal_tags.append("explicit_ask")
        if any(word in text for word in ("prototype", "wireframe", "mvp")):
            signal_tags.append("prototype")
        if any(word in text for word in ("roadmap", "plan")):
            signal_tags.append("roadmap")
        if any(word in text for word in ("handoff", "design", "ux")):
            signal_tags.append("design_handoff")
        if has_gap_signal:
            signal_tags.append("build_gap")
        if "founder" in text or "cofounder" in text:
            signal_tags.append("decision_maker_visible")
        if any(word in text for word in ("no engineering team", "no obvious engineering team")):
            signal_tags.append("no_obvious_eng_team")
        if any(word in text for word in ("project-based", "milestone-based", "scope")):
            signal_tags.append("project_shaped")
        if any(word in text for word in ("launch", "launch-ready", "launching")):
            signal_tags.append("launch_pressure")
        if has_live_signal and has_gap_signal:
            signal_tags.append("existing_system_transition")
        if decision_access_signal >= 4:
            signal_tags.append("decision_access_visible")
        if scope_freedom_signal >= 4:
            signal_tags.append("scope_shaping_room")
        if stage_signal >= 4:
            signal_tags.append("early_stage_signal")

        risk_tags: list[str] = []
        if any(word in text for word in ("hire", "recruiter", "job post")):
            risk_tags.append("hiring")
        if staff_aug_risk:
            risk_tags.append("staff_aug")
        if advisory_risk:
            risk_tags.append("advisory_only")
        if maintenance_risk:
            risk_tags.append("maintenance")
        if mature_org_risk:
            risk_tags.append("mature_team")
        if decision_access_unclear:
            risk_tags.append("decision_access_unclear")
        if any(word in text for word in ("equity-only", "equity only")):
            risk_tags.append("equity_only")
        if any(word in text for word in ("cofounder", "technical cofounder")):
            risk_tags.append("cofounder")
        if has_live_signal and not has_gap_signal:
            risk_tags.append("existing_product_no_gap")

        fatal_risk_tags = {"hiring", "staff_aug", "advisory_only", "maintenance", "equity_only"}
        if profile_fit == "low" or any(tag in fatal_risk_tags for tag in risk_tags):
            action_queue = "decline"
        elif activation_signal == "explicit" and evidence_confidence != "thin":
            action_queue = "pursue_now"
        elif profile_fit == "high" and evidence_confidence != "thin":
            action_queue = "nurture" if target.kind == "connector" or activation_signal == "weak" else "watch"
        elif profile_fit == "medium" and evidence_confidence != "thin":
            action_queue = "watch"
        else:
            action_queue = "decline"

        summary_thesis = (
            "Public signals point to project-shaped software work with room for an external builder."
            if action_queue != "decline"
            else "The public signals do not justify surfacing this as an active opportunity."
        )
        fit_rationale = (
            "Signals point to roadmap, prototype, or transition-stage product work with room for one accountable builder."
            if action_queue != "decline"
            else "The available signals are too weak or too misaligned with the profile to justify surfacing this today."
        )
        activation_rationale = (
            "Recent language or an explicit ask suggests this is a better-than-average moment to reach out."
            if action_queue == "pursue_now"
            else "There is not enough visible urgency or explicit activation to justify immediate outreach."
        )
        outreach_angle = ""
        draft_subject = ""
        draft_body = ""
        if action_queue == "pursue_now":
            outreach_angle = (
                "Offer to help turn early product direction into a launch-ready first version."
                if target.kind == "founder"
                else "Offer to be the trusted builder after strategy or design work is complete."
            )
            draft_subject = (
                f"A builder you can keep in mind for product delivery"
                if target.kind == "connector"
                else f"Possible fit for product build work at {target.name}"
            )
            draft_body = (
                f"I run a solo product engineering practice focused on helping teams turn ideas, roadmaps, and prototypes into real customer-facing software.\n\n"
                f"{outreach_angle}\n\n"
                "If that seems relevant, I’d be glad to compare notes."
            )

        unknowns_to_verify: list[str] = []
        if "budget" not in text:
            unknowns_to_verify.append("budget and commercial scope")
        if decision_access_unclear:
            unknowns_to_verify.append("direct decision-maker access")
        if target.kind == "founder" and has_live_signal and not has_gap_signal:
            unknowns_to_verify.append("scope constraints around the existing product")
        if target.kind == "connector":
            unknowns_to_verify.append("direct buyer introduction path")
        unknowns_to_verify.append("handoff owner and post-launch ownership")

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
            confidence=0.75 if action_queue != "decline" else 0.45,
            profile_fit=profile_fit,
            activation_signal=activation_signal,
            evidence_confidence=evidence_confidence,
            freshness=freshness,
            action_queue=action_queue,
            summary_thesis=summary_thesis,
            fit_rationale=fit_rationale,
            activation_rationale=activation_rationale,
            outreach_angle=outreach_angle,
            draft_subject=draft_subject,
            draft_body=draft_body,
            signal_tags=signal_tags,
            risk_tags=risk_tags,
            unknowns_to_verify=unknowns_to_verify,
            evidence=evidence,
            raw_response={"provider": self.name, "mode": "heuristic"},
        )


def _feedback_tokens(text: str) -> set[str]:
    tokens = {token for token in text.split() if len(token) >= 5}
    return tokens
