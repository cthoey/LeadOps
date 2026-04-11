from __future__ import annotations

from typing import Protocol

from leadops.models import AssessmentResult
from leadops.repository import TargetRecord
from leadops.config import WorkspaceConfig
from leadops.approaches import ApproachSpec


class Provider(Protocol):
    name: str

    def assess(
        self,
        target: TargetRecord,
        config: WorkspaceConfig,
        approach: ApproachSpec | None = None,
        feedback_context: dict[str, list[dict[str, str]]] | None = None,
    ) -> AssessmentResult:
        raise NotImplementedError
