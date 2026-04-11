from __future__ import annotations

import json
import sys


def main() -> int:
    payload = json.loads(sys.stdin.read())
    target = payload["target"]
    name = target["name"]
    result = {
        "confidence": 0.91,
        "profile_fit": "high",
        "activation_signal": "explicit",
        "evidence_confidence": "strong",
        "freshness": "fresh",
        "action_queue": "pursue_now",
        "summary_thesis": f"{name} looks like a strong public match for immediate outreach.",
        "fit_rationale": f"{name} matches the profile based on the visible work shape and evidence.",
        "activation_rationale": "Signals suggest timely outreach.",
        "outreach_angle": "Offer build ownership from roadmap to launch.",
        "draft_subject": f"Possible fit for early product build work at {name}",
        "draft_body": "Short draft body.",
        "signal_tags": ["explicit_ask", "build_gap"],
        "risk_tags": [],
        "unknowns_to_verify": ["budget and buyer authority"],
        "evidence": ["Test evidence"],
        "source_date": "2026-04-09",
    }
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
