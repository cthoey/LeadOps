from __future__ import annotations

import json
import subprocess

from leadops.approaches import ApproachSpec
from leadops.config import WorkspaceConfig
from leadops.models import AssessmentResult, assessment_from_dict
from leadops.repository import TargetRecord


class CommandProvider:
    name = "command"

    def assess(
        self,
        target: TargetRecord,
        config: WorkspaceConfig,
        approach: ApproachSpec | None = None,
        feedback_context: dict[str, list[dict[str, str]]] | None = None,
    ) -> AssessmentResult:
        if not config.llm.command:
            raise RuntimeError("Command provider selected but no command is configured.")

        payload = {
            "profile": {
                "name": config.profile.name,
                "offer": config.profile.offer,
                "ideal_customer": config.profile.ideal_customer,
                "fit_definition": config.profile.fit_definition,
                "preferred_signals": config.profile.preferred_signals,
                "caution_signals": config.profile.caution_signals,
                "post_contact_checks": config.profile.post_contact_checks,
                "hard_rejects": config.profile.hard_rejects,
                "daily_new_lead_cap": config.profile.daily_new_lead_cap,
            },
            "approach": approach.as_payload() if approach else {},
            "feedback": feedback_context or {"liked": [], "avoided": []},
            "target": {
                "id": target.id,
                "kind": target.kind,
                "name": target.name,
                "url": target.url,
                "source": target.source,
                "notes": target.notes,
                "raw_evidence": target.raw_evidence,
                "status": target.status,
            },
        }
        completed = subprocess.run(
            config.llm.command,
            input=json.dumps(payload),
            capture_output=True,
            check=False,
            text=True,
            timeout=config.llm.timeout_seconds,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Command provider failed with exit code {completed.returncode}: {completed.stderr.strip()}"
            )
        raw = json.loads(completed.stdout)
        result = assessment_from_dict(raw)
        result.raw_response = raw
        return result
