from __future__ import annotations

import json
import sys


def main() -> int:
    payload = json.loads(sys.stdin.read())
    target = payload["target"]
    name = target["name"]
    result = {
        "recommend": True,
        "confidence": 0.91,
        "rubric": {
            "work_shape_fit": 5,
            "founder_proximity": 4,
            "one_builder_fit": 5,
            "stage_fit": 4,
            "autonomy_fit": 4,
            "product_excitement": 4,
            "urgency_timing": 3,
            "evidence_strength": 4,
            "staff_aug_risk": 0,
            "advisory_smell": 0,
            "maintenance_gravity": 0,
            "big_team_risk": 0,
            "buyer_access_unclear": 0,
            "weak_evidence": 0,
            "low_enjoyment": 0,
        },
        "why_fit": f"{name} is a strong fit for founder-side early product work.",
        "why_now": "Signals suggest timely outreach.",
        "outreach_angle": "Offer build ownership from roadmap to launch.",
        "draft_subject": f"Possible fit for early product build work at {name}",
        "draft_body": "Short draft body.",
        "risks": [],
        "evidence": ["Test evidence"],
    }
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
