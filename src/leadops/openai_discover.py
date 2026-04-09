from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from leadops.assessment_contract import compact_response_metadata, extract_output_text
from leadops.discovery_contract import provider_payload
from leadops.models import discovery_batch_from_dict


RESPONSES_URL = "https://api.openai.com/v1/responses"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m leadops.openai_discover",
        description="LeadOps bridge that reads a discovery payload from stdin and returns discovered candidates JSON.",
    )
    parser.add_argument("--model", required=True, help="OpenAI model id to use.")
    parser.add_argument(
        "--reasoning-effort",
        choices=["none", "low", "medium", "high", "xhigh"],
        help="Optional reasoning effort.",
    )
    parser.add_argument("--max-output-tokens", type=int, default=5000)
    parser.add_argument("--api-key-env", default="OPENAI_API_KEY", help="Environment variable containing the API key.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    api_key = os.environ.get(args.api_key_env, "").strip()
    if not api_key:
        raise SystemExit(f"Missing API key in ${args.api_key_env}.")

    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("Expected a JSON payload on stdin.")
    search_payload = json.loads(raw)

    request_body = {
        "model": args.model,
        "max_output_tokens": args.max_output_tokens,
        **provider_payload(search_payload),
    }
    if args.reasoning_effort:
        request_body["reasoning"] = {"effort": args.reasoning_effort}

    response_payload = _post_json(RESPONSES_URL, request_body, api_key)
    try:
        output_text = extract_output_text(response_payload)
    except ValueError as exc:
        raise SystemExit(
            "OpenAI discovery response did not contain a final structured message. "
            f"status={response_payload.get('status')} "
            f"incomplete_details={response_payload.get('incomplete_details')} "
            f"output_types={[item.get('type') for item in response_payload.get('output', [])]} "
            f"error={response_payload.get('error')} "
            f"({exc})"
        ) from exc
    discovery = json.loads(output_text)
    validated = discovery_batch_from_dict(discovery)
    emitted = validated.as_dict()
    emitted["raw_response"] = compact_response_metadata(response_payload)
    sys.stdout.write(json.dumps(emitted))
    sys.stdout.flush()
    return 0


def _post_json(url: str, payload: dict[str, Any], api_key: str) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"OpenAI API returned HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise SystemExit(f"Could not reach OpenAI API: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
