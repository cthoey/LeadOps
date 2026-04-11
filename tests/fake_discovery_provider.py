from __future__ import annotations

import json
import sys


def main() -> int:
    payload = json.loads(sys.stdin.read())
    query = payload["search"]["query"]
    emitted = {
        "candidates": [
            {
                "name": "Proto Foundry",
                "url": "https://protofoundry.example",
                "confidence": 0.93,
                "profile_fit": "high",
                "activation_signal": "explicit",
                "evidence_confidence": "strong",
                "freshness": "fresh",
                "summary_thesis": "Strong public signs point to project-shaped software work worth reviewing.",
                "fit_rationale": f"Visible public signals align well with the search: {query}",
                "activation_rationale": "Recent prototype-stage messaging and launch intent are visible.",
                "evidence": [
                    "Founder describes the product as a prototype heading toward launch.",
                    "No visible hiring or staff-augmentation framing.",
                ],
                "source_urls": [
                    "https://protofoundry.example",
                    "https://signals.example/protofoundry",
                ],
                "signal_tags": [
                    "prototype",
                    "launch_pressure",
                ],
                "risk_tags": [
                    "Budget is not visible from public evidence.",
                ],
                "source_date": "2026-04-09",
            }
        ],
        "raw_response": {
            "id": "fake-discovery",
            "model": "fake",
            "status": "completed",
        },
    }
    sys.stdout.write(json.dumps(emitted))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
