from __future__ import annotations

import argparse
from contextlib import closing
import json
from pathlib import Path

from leadops.approaches import ApproachSpec, get_approach, list_approaches
from leadops.briefs import BriefItem, render_email_html, render_email_subject
from leadops.config import config_path, initialize_workspace, load_workspace_config
from leadops.daily import run_daily
from leadops.db import connect, initialize_database
from leadops.discovery import DiscoveryTrackResult, discover_track, discover_web
from leadops.extract import fetch_and_extract
from leadops.mailer import send_email_digest
from leadops.models import assessment_from_dict
from leadops.query_plans import TRACKS, get_track, list_tracks
from leadops.repository import Repository, TARGET_STATUSES, TargetRecord
from leadops.schedule import (
    DEFAULT_LABEL,
    LaunchdSpec,
    build_program_arguments,
    default_launch_agent_path,
    install_launchd_spec,
    render_launchd_plist,
)
from leadops.util import today_iso


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="leadops", description="Daily precision lead curation.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_workspace = subparsers.add_parser("init-workspace", help="Create a LeadOps workspace.")
    init_workspace.add_argument("path", help="Workspace path.")

    add_target = subparsers.add_parser("add-target", help="Add one manual target.")
    add_target.add_argument("--workspace", required=True, help="Workspace path.")
    add_target.add_argument("--kind", required=True, choices=["connector", "founder"])
    add_target.add_argument("--name", required=True)
    add_target.add_argument("--url", default="")
    add_target.add_argument("--source", required=True)
    add_target.add_argument("--notes", default="")
    add_target.add_argument("--raw-evidence", default="")

    ingest_url = subparsers.add_parser("ingest-url", help="Fetch a public URL and turn it into a target candidate.")
    ingest_url.add_argument("--workspace", required=True, help="Workspace path.")
    ingest_url.add_argument("--kind", required=True, choices=["connector", "founder"])
    ingest_url.add_argument("--url", required=True)
    ingest_url.add_argument("--name", default="")
    ingest_url.add_argument("--source", default="web")
    ingest_url.add_argument("--notes", default="")

    import_jsonl = subparsers.add_parser("import-jsonl", help="Import targets from a JSONL file.")
    import_jsonl.add_argument("--workspace", required=True, help="Workspace path.")
    import_jsonl.add_argument("path", help="JSONL file path.")

    discover_web_cmd = subparsers.add_parser("discover-web", help="Run a bounded web discovery pass and ingest candidates.")
    discover_web_cmd.add_argument("--workspace", required=True, help="Workspace path.")
    discover_web_cmd.add_argument("--kind", required=True, choices=["connector", "founder"])
    discover_web_cmd.add_argument("--query", required=True, help="Search query for discovery.")
    discover_web_cmd.add_argument("--limit", type=int, default=5, help="Maximum candidates to ingest.")
    discover_web_cmd.add_argument("--source", default="web-discovery", help="Source label to store on discovered targets.")
    discover_web_cmd.add_argument("--approach", choices=[spec.name for spec in list_approaches()], help="Optional lead-finding approach.")

    subparsers.add_parser("list-tracks", help="List built-in discovery tracks.")
    subparsers.add_parser("list-approaches", help="List built-in lead-finding approaches.")

    discover_track_cmd = subparsers.add_parser(
        "discover-track",
        help="Run a built-in discovery track made of several hyper-aligned queries.",
    )
    discover_track_cmd.add_argument("--workspace", required=True, help="Workspace path.")
    discover_track_cmd.add_argument("--track", required=True, choices=sorted(TRACKS))
    discover_track_cmd.add_argument(
        "--per-query-limit",
        type=int,
        default=None,
        help="Override the per-query candidate cap.",
    )
    discover_track_cmd.add_argument(
        "--source-prefix",
        default="web-discovery",
        help="Source prefix to store on discovered targets.",
    )
    discover_track_cmd.add_argument(
        "--approach",
        choices=[spec.name for spec in list_approaches()],
        help="Optional lead-finding approach to provide extra strategy context during discovery.",
    )

    discover_approach_cmd = subparsers.add_parser(
        "discover-approach",
        help="Run one named lead-finding approach made of several tracks.",
    )
    discover_approach_cmd.add_argument("--workspace", required=True, help="Workspace path.")
    discover_approach_cmd.add_argument("--approach", required=True, choices=[spec.name for spec in list_approaches()])
    discover_approach_cmd.add_argument(
        "--per-query-limit",
        type=int,
        default=None,
        help="Override the approach's default per-query candidate cap.",
    )
    discover_approach_cmd.add_argument(
        "--source-prefix",
        default="web-discovery",
        help="Source prefix to store on discovered targets.",
    )

    run_daily_cmd = subparsers.add_parser("run-daily", help="Run one daily curation pass.")
    run_daily_cmd.add_argument("--workspace", required=True, help="Workspace path.")
    run_daily_cmd.add_argument("--date", default=today_iso(), help="Packet date in YYYY-MM-DD.")
    run_daily_cmd.add_argument(
        "--approach",
        choices=[spec.name for spec in list_approaches()],
        help="Optional lead-finding approach to run before assessment and pass through as retrieval context.",
    )
    run_daily_cmd.add_argument(
        "--discover-track",
        action="append",
        default=[],
        choices=sorted(TRACKS),
        help="Optional built-in discovery track(s) to run before assessment.",
    )
    run_daily_cmd.add_argument(
        "--discover-per-query-limit",
        type=int,
        default=None,
        help="Override per-query limit for any discovery tracks run before the packet.",
    )
    run_daily_cmd.add_argument(
        "--send-digest",
        action="store_true",
        help="Send the daily digest email after the packet is generated.",
    )

    list_targets = subparsers.add_parser("list-targets", help="List targets in the workspace.")
    list_targets.add_argument("--workspace", required=True, help="Workspace path.")

    mark_status = subparsers.add_parser("mark-status", help="Update a target status.")
    mark_status.add_argument("--workspace", required=True, help="Workspace path.")
    mark_status.add_argument("target_id", type=int)
    mark_status.add_argument("status", choices=sorted(TARGET_STATUSES))
    mark_status.add_argument("--followup-date", default=None)
    mark_status.add_argument("--reason", default="")

    feedback_summary = subparsers.add_parser(
        "feedback-summary",
        help="Show the recent decisions fed back into discovery and assessment context.",
    )
    feedback_summary.add_argument("--workspace", required=True, help="Workspace path.")
    feedback_summary.add_argument("--limit-per-action", type=int, default=3)

    send_digest = subparsers.add_parser("send-digest", help="Send an existing daily digest email.")
    send_digest.add_argument("--workspace", required=True, help="Workspace path.")
    send_digest.add_argument("--date", default=today_iso(), help="Packet date in YYYY-MM-DD.")

    print_launchd = subparsers.add_parser("print-launchd", help="Print a launchd plist for a scheduled daily run.")
    _add_launchd_arguments(print_launchd)

    install_launchd = subparsers.add_parser("install-launchd", help="Install a launchd agent for a scheduled daily run.")
    _add_launchd_arguments(install_launchd)
    install_launchd.add_argument(
        "--no-load",
        action="store_true",
        help="Write the plist but do not load it with launchctl.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "init-workspace":
        workspace = initialize_workspace(Path(args.path))
        initialize_database(workspace / "var" / "leadops.db")
        print(f"Initialized workspace: {workspace}")
        print(f"Config: {workspace / 'leadops.toml'}")
        print(f"Database: {workspace / 'var' / 'leadops.db'}")
        return 0

    if args.command == "add-target":
        with closing(_repo_for_workspace(Path(args.workspace))) as repo:
            target_id, action = repo.add_or_update_target(
                kind=args.kind,
                name=args.name,
                url=args.url.strip() or None,
                source=args.source,
                notes=args.notes,
                raw_evidence=args.raw_evidence,
            )
        print(f"{action.capitalize()} target {target_id}: {args.name}")
        return 0

    if args.command == "ingest-url":
        with closing(_repo_for_workspace(Path(args.workspace))) as repo:
            extracted = fetch_and_extract(args.url)
            name = args.name.strip() or extracted.lead_name()
            notes_parts = [part for part in [args.notes.strip(), extracted.meta_description.strip()] if part]
            target_id, action = repo.add_or_update_target(
                kind=args.kind,
                name=name,
                url=extracted.final_url,
                source=args.source,
                notes="\n\n".join(notes_parts),
                raw_evidence=extracted.raw_evidence(),
            )
        print(f"{action.capitalize()} target {target_id}: {name}")
        print(f"Final URL: {extracted.final_url}")
        if extracted.title:
            print(f"Title: {extracted.title}")
        return 0

    if args.command == "import-jsonl":
        with closing(_repo_for_workspace(Path(args.workspace))) as repo:
            created, updated = repo.import_jsonl(Path(args.path).expanduser())
        print(f"Imported targets from {args.path}")
        print(f"Created: {created}")
        print(f"Updated: {updated}")
        return 0

    if args.command == "discover-web":
        workspace = Path(args.workspace).expanduser().resolve()
        config = _load_existing_workspace_config(workspace)
        with closing(_repo_for_workspace(workspace)) as repo:
            approach = get_approach(args.approach) if args.approach else None
            result = discover_web(
                repo,
                config,
                query=args.query,
                kind=args.kind,
                limit=max(1, args.limit),
                source=args.source,
                approach=approach,
            )
        print(f"Discovery complete for query run {result.query_run_id}")
        print(f"Candidates returned: {result.total_candidates}")
        print(f"Created: {result.created}")
        print(f"Updated: {result.updated}")
        return 0

    if args.command == "list-tracks":
        for track in list_tracks():
            print(f"{track.name}\t{track.description}")
            for spec in track.queries:
                print(f"  - {spec.name}\t{spec.kind}\t{spec.query}")
        return 0

    if args.command == "list-approaches":
        for approach in list_approaches():
            print(f"{approach.name}\t{approach.label}\t{approach.description}")
            print(f"  - tracks\t{', '.join(approach.discover_tracks)}")
            print(f"  - strategy\t{approach.strategy}")
        return 0

    if args.command == "discover-track":
        workspace = Path(args.workspace).expanduser().resolve()
        config = _load_existing_workspace_config(workspace)
        with closing(_repo_for_workspace(workspace)) as repo:
            approach = get_approach(args.approach) if hasattr(args, "approach") and args.approach else None
            result = discover_track(
                repo,
                config,
                track=get_track(args.track),
                limit_override=args.per_query_limit,
                source_prefix=args.source_prefix,
                approach=approach,
            )
        _print_track_result(result)
        return 0

    if args.command == "discover-approach":
        workspace = Path(args.workspace).expanduser().resolve()
        config = _load_existing_workspace_config(workspace)
        with closing(_repo_for_workspace(workspace)) as repo:
            approach = get_approach(args.approach)
            result = _run_approach_discovery(
                repo,
                config,
                approach=approach,
                per_query_limit=args.per_query_limit,
                source_prefix=args.source_prefix,
            )
        _print_approach_result(approach.label, result)
        return 0

    if args.command == "run-daily":
        workspace = Path(args.workspace).expanduser().resolve()
        config = _load_existing_workspace_config(workspace)
        with closing(_repo_for_workspace(workspace)) as repo:
            explicit_approach = bool(args.approach)
            approach = get_approach(args.approach) if args.approach else None
            if explicit_approach:
                approach_result = _run_approach_discovery(
                    repo,
                    config,
                    approach=approach,
                    per_query_limit=args.discover_per_query_limit,
                )
                _print_approach_result(approach.label, approach_result)
            for track_name in args.discover_track:
                track_result = discover_track(
                    repo,
                    config,
                    track=get_track(track_name),
                    limit_override=args.discover_per_query_limit,
                    approach=approach,
                )
                _print_track_result(track_result)
            result = run_daily(repo, config, args.date, approach=approach, send_digest=args.send_digest)
        print(f"Run complete for {args.date}")
        print(f"Approach: {approach.label if approach else '(none)'}")
        print(f"New targets surfaced: {result.surfaced_new}")
        print(f"Follow-ups surfaced: {result.surfaced_followups}")
        print(f"Markdown brief: {result.packet_markdown}")
        print(f"JSON brief: {result.packet_json}")
        print(f"Digest text: {result.digest_text}")
        print(f"Digest HTML: {result.digest_html}")
        print(f"Current review markdown: {result.current_review_markdown}")
        print(f"Current review JSON: {result.current_review_json}")
        print(f"Current review text: {result.current_review_text}")
        print(f"Current review HTML: {result.current_review_html}")
        print(f"Digest sent: {'yes' if result.digest_sent else 'no'}")
        return 0

    if args.command == "list-targets":
        with closing(_repo_for_workspace(Path(args.workspace))) as repo:
            for target in repo.list_targets():
                print(
                    f"{target.id}\t{target.kind}\t{target.status}\t{target.name}\t{target.source}\t{target.url or '-'}"
                )
        return 0

    if args.command == "mark-status":
        with closing(_repo_for_workspace(Path(args.workspace))) as repo:
            repo.update_status(
                args.target_id,
                status=args.status,
                followup_date=args.followup_date,
                reason=args.reason,
            )
        print(f"Updated target {args.target_id} -> {args.status}")
        return 0

    if args.command == "feedback-summary":
        with closing(_repo_for_workspace(Path(args.workspace))) as repo:
            payload = repo.feedback_context_payload(limit_per_action=max(1, args.limit_per_action))
        print("Liked / advanced patterns:")
        if payload["liked"]:
            for item in payload["liked"]:
                print(f"- [{item['action']}] {item['name']}: {item['reason'] or item['summary'] or '(no rationale)'}")
        else:
            print("- none")
        print("")
        print("Avoided patterns:")
        if payload["avoided"]:
            for item in payload["avoided"]:
                print(f"- [{item['action']}] {item['name']}: {item['reason'] or item['summary'] or '(no rationale)'}")
        else:
            print("- none")
        return 0

    if args.command == "send-digest":
        workspace = Path(args.workspace).expanduser().resolve()
        config = _load_existing_workspace_config(workspace)
        packet_dir = config.outbox_dir / args.date
        digest_path = packet_dir / "daily-digest.txt"
        digest_html_path = packet_dir / "daily-digest.html"
        json_path = packet_dir / "daily-brief.json"
        if not digest_path.exists():
            raise SystemExit(f"Missing digest file: {digest_path}")
        if not json_path.exists():
            raise SystemExit(f"Missing packet JSON: {json_path}")
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        subject = _email_subject_from_packet_payload(args.date, payload)
        body_html = digest_html_path.read_text(encoding="utf-8") if digest_html_path.exists() else _email_html_from_payload(
            args.date, payload
        )
        send_email_digest(
            email_config=config.email,
            subject=subject,
            body_text=digest_path.read_text(encoding="utf-8"),
            body_html=body_html,
        )
        print(f"Sent digest for {args.date}")
        print(f"Digest file: {digest_path}")
        print(f"Digest HTML: {digest_html_path if digest_html_path.exists() else '(generated in memory)'}")
        return 0

    if args.command == "print-launchd":
        spec = _launchd_spec_from_args(args)
        print(render_launchd_plist(spec))
        return 0

    if args.command == "install-launchd":
        spec = _launchd_spec_from_args(args)
        install_launchd_spec(spec, load=not args.no_load)
        print(f"Installed launchd agent: {spec.label}")
        print(f"Plist: {spec.plist_path}")
        print(f"Stdout log: {spec.stdout_path}")
        print(f"Stderr log: {spec.stderr_path}")
        print(f"Loaded: {'no' if args.no_load else 'yes'}")
        return 0

    parser.error("Unknown command")
    return 2


def _repo_for_workspace(workspace: Path) -> Repository:
    workspace = workspace.expanduser().resolve()
    config = _load_existing_workspace_config(workspace)
    initialize_database(config.database_path)
    return Repository(connect(config.database_path))


def _load_existing_workspace_config(workspace: Path):
    workspace = workspace.expanduser().resolve()
    try:
        return load_workspace_config(workspace)
    except FileNotFoundError as exc:
        raise SystemExit(
            f"Missing workspace config: {config_path(workspace)}. "
            f"Run `leadops init-workspace {workspace}` first."
        ) from exc


def _print_track_result(result: DiscoveryTrackResult) -> None:
    print(f"Discovery track complete: {result.track_name}")
    print(f"Candidates returned: {result.total_candidates}")
    print(f"Created: {result.total_created}")
    print(f"Updated: {result.total_updated}")
    for item in result.results:
        print(
            f"- {item.query_name} ({item.kind})"
            f": candidates={item.total_candidates} created={item.created} updated={item.updated}"
        )


def _run_approach_discovery(
    repo: Repository,
    config,
    *,
    approach,
    per_query_limit: int | None,
    source_prefix: str = "web-discovery",
) -> list[DiscoveryTrackResult]:
    results: list[DiscoveryTrackResult] = []
    limit_override = per_query_limit if per_query_limit is not None else approach.default_per_query_limit
    for track_name in approach.discover_tracks:
        result = discover_track(
            repo,
            config,
            track=get_track(track_name),
            limit_override=limit_override,
            source_prefix=source_prefix,
            approach=approach,
        )
        results.append(result)
    return results


def _print_approach_result(approach_label: str, results: list[DiscoveryTrackResult]) -> None:
    print(f"Discovery approach complete: {approach_label}")
    print(
        "Summary:"
        f" tracks={len(results)}"
        f" candidates={sum(result.total_candidates for result in results)}"
        f" created={sum(result.total_created for result in results)}"
        f" updated={sum(result.total_updated for result in results)}"
    )
    for result in results:
        _print_track_result(result)


def _email_subject_from_packet_payload(packet_date: str, payload: dict[str, object]) -> str:
    queues = _queues_from_payload(payload)
    return render_email_subject(
        packet_date,
        new_items=[None] * sum(len(items) for queue_name, items in queues.items() if queue_name != "followup_due"),
        followup_items=[None] * len(queues.get("followup_due", [])),
    )


def _email_html_from_payload(packet_date: str, payload: dict[str, object]) -> str:
    run_context = payload.get("run_context", {})
    approach = _approach_from_payload(run_context.get("approach")) if isinstance(run_context, dict) else None
    queues = _queues_from_payload(payload)
    return render_email_html(
        packet_date,
        new_items=[
            _brief_item_from_payload(item, queue_name)
            for queue_name in ("pursue_now", "watch", "nurture")
            for item in queues.get(queue_name, [])
        ],
        followup_items=[_brief_item_from_payload(item, "followup_due") for item in queues.get("followup_due", [])],
        approach=approach,
    )


def _brief_item_from_payload(item: dict[str, object], section: str) -> BriefItem:
    target_payload = item.get("target", {})
    assessment_payload = item.get("assessment", {})
    target = TargetRecord(
        id=int(target_payload.get("id", 0)),
        kind=str(target_payload.get("kind", "")),
        name=str(target_payload.get("name", "")),
        url=str(target_payload.get("url", "") or ""),
        source=str(target_payload.get("source", "")),
        notes=str(target_payload.get("notes", "")),
        raw_evidence=str(target_payload.get("raw_evidence", "")),
        status=str(target_payload.get("status", "")),
        domain="",
        dedupe_key="",
        last_packeted_at=None,
        next_followup_at=str(target_payload.get("next_followup_at", "") or "") or None,
    )
    assessment = assessment_from_dict(dict(assessment_payload))
    return BriefItem(
        target=target,
        assessment=assessment,
        section=section,
        rank_index=int(item.get("rank_index", 0)),
    )


def _approach_from_payload(payload: object) -> ApproachSpec | None:
    if not isinstance(payload, dict):
        return None
    name = str(payload.get("name", "") or "").strip()
    label = str(payload.get("label", "") or name).strip()
    if not name:
        return None
    return ApproachSpec(
        name=name,
        label=label,
        description=str(payload.get("description", "") or ""),
        strategy=str(payload.get("strategy", "") or ""),
        discover_tracks=tuple(str(item) for item in payload.get("discover_tracks", []) if str(item).strip()),
        prioritize=tuple(str(item) for item in payload.get("prioritize", []) if str(item).strip()),
        reject=tuple(str(item) for item in payload.get("reject", []) if str(item).strip()),
        default_per_query_limit=int(payload.get("default_per_query_limit", 2) or 2),
    )


def _queues_from_payload(payload: dict[str, object]) -> dict[str, list[dict[str, object]]]:
    queues = payload.get("queues", {})
    if not isinstance(queues, dict):
        return {}
    normalized: dict[str, list[dict[str, object]]] = {}
    for queue_name, items in queues.items():
        if not isinstance(items, list):
            continue
        normalized[str(queue_name)] = [item for item in items if isinstance(item, dict)]
    return normalized


def _add_launchd_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True, help="Workspace path.")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="Launchd label.")
    parser.add_argument("--hour", type=int, default=8, help="Hour in local time.")
    parser.add_argument("--minute", type=int, default=0, help="Minute in local time.")
    parser.add_argument(
        "--time",
        action="append",
        default=[],
        help="Run time in local HH:MM. Repeat to schedule multiple runs per day.",
    )
    parser.add_argument(
        "--approach",
        choices=[spec.name for spec in list_approaches()],
        help="Optional lead-finding approach to run during the scheduled pass.",
    )
    parser.add_argument(
        "--discover-track",
        action="append",
        default=[],
        choices=sorted(TRACKS),
        help="Additional built-in discovery track(s) to run before the packet.",
    )
    parser.add_argument(
        "--discover-per-query-limit",
        type=int,
        default=2,
        help="Per-query candidate cap for scheduled discovery.",
    )
    parser.add_argument(
        "--no-send-digest",
        action="store_true",
        help="Do not send the digest after the scheduled run.",
    )


def _launchd_spec_from_args(args: argparse.Namespace) -> LaunchdSpec:
    workspace = Path(args.workspace).expanduser().resolve()
    _load_existing_workspace_config(workspace)
    repo_root = Path(__file__).resolve().parents[2]
    logs_dir = workspace / "var" / "log"
    label = str(args.label).strip() or DEFAULT_LABEL
    times = _parse_launchd_times(getattr(args, "time", []), default_hour=int(args.hour), default_minute=int(args.minute))
    return LaunchdSpec(
        label=label,
        plist_path=default_launch_agent_path(label),
        times=times,
        program_arguments=build_program_arguments(
            repo_root=repo_root,
            workspace=workspace,
            approach_name=args.approach,
            discover_tracks=list(args.discover_track),
            discover_per_query_limit=args.discover_per_query_limit,
            send_digest=not args.no_send_digest,
        ),
        working_directory=repo_root,
        stdout_path=logs_dir / "launchd.stdout.log",
        stderr_path=logs_dir / "launchd.stderr.log",
    )


def _parse_launchd_times(raw_times: list[str], *, default_hour: int, default_minute: int) -> tuple[tuple[int, int], ...]:
    if not raw_times:
        return ((default_hour, default_minute),)

    parsed: list[tuple[int, int]] = []
    for raw in raw_times:
        value = str(raw).strip()
        if not value:
            continue
        hour_text, separator, minute_text = value.partition(":")
        if separator != ":":
            raise SystemExit(f"Invalid --time value '{value}'. Expected HH:MM.")
        try:
            hour = int(hour_text)
            minute = int(minute_text)
        except ValueError as exc:
            raise SystemExit(f"Invalid --time value '{value}'. Expected HH:MM.") from exc
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise SystemExit(f"Invalid --time value '{value}'. Expected HH:MM in 24-hour local time.")
        parsed.append((hour, minute))

    unique = tuple(sorted(set(parsed)))
    if not unique:
        raise SystemExit("At least one valid --time value is required.")
    return unique
