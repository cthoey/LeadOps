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
                "fit_score": 91,
                "why_fit": f"Strong founder-side build fit surfaced for query: {query}",
                "why_now": "Recent prototype-stage messaging and launch intent are visible.",
                "evidence": [
                    "Founder describes the product as a prototype heading toward launch.",
                    "No visible hiring or staff-augmentation framing.",
                ],
                "source_urls": [
                    "https://protofoundry.example",
                    "https://signals.example/protofoundry",
                ],
                "risks": [
                    "Budget is not visible from public evidence.",
                ],
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
