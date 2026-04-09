from __future__ import annotations

import argparse
import json
from pathlib import Path

from leadops.briefs import render_email_subject
from leadops.config import initialize_workspace, load_workspace_config
from leadops.daily import run_daily
from leadops.db import connect, initialize_database
from leadops.discovery import DiscoveryTrackResult, discover_track, discover_web
from leadops.extract import fetch_and_extract
from leadops.mailer import send_email_digest
from leadops.query_plans import TRACKS, get_track, list_tracks
from leadops.repository import Repository, TARGET_STATUSES
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

    subparsers.add_parser("list-tracks", help="List built-in discovery tracks.")

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

    run_daily_cmd = subparsers.add_parser("run-daily", help="Run one daily curation pass.")
    run_daily_cmd.add_argument("--workspace", required=True, help="Workspace path.")
    run_daily_cmd.add_argument("--date", default=today_iso(), help="Packet date in YYYY-MM-DD.")
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

    feedback_summary = subparsers.add_parser("feedback-summary", help="Show the recent decisions fed back into ranking.")
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
        repo = _repo_for_workspace(Path(args.workspace))
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
        repo = _repo_for_workspace(Path(args.workspace))
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
        repo = _repo_for_workspace(Path(args.workspace))
        created, updated = repo.import_jsonl(Path(args.path).expanduser())
        print(f"Imported targets from {args.path}")
        print(f"Created: {created}")
        print(f"Updated: {updated}")
        return 0

    if args.command == "discover-web":
        workspace = Path(args.workspace).expanduser().resolve()
        config = load_workspace_config(workspace)
        repo = _repo_for_workspace(workspace)
        result = discover_web(
            repo,
            config,
            query=args.query,
            kind=args.kind,
            limit=max(1, args.limit),
            source=args.source,
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

    if args.command == "discover-track":
        workspace = Path(args.workspace).expanduser().resolve()
        config = load_workspace_config(workspace)
        repo = _repo_for_workspace(workspace)
        result = discover_track(
            repo,
            config,
            track=get_track(args.track),
            limit_override=args.per_query_limit,
            source_prefix=args.source_prefix,
        )
        _print_track_result(result)
        return 0

    if args.command == "run-daily":
        workspace = Path(args.workspace).expanduser().resolve()
        config = load_workspace_config(workspace)
        repo = _repo_for_workspace(workspace)
        for track_name in args.discover_track:
            track_result = discover_track(
                repo,
                config,
                track=get_track(track_name),
                limit_override=args.discover_per_query_limit,
            )
            _print_track_result(track_result)
        result = run_daily(repo, config, args.date, send_digest=args.send_digest)
        print(f"Run complete for {args.date}")
        print(f"New targets surfaced: {result.surfaced_new}")
        print(f"Follow-ups surfaced: {result.surfaced_followups}")
        print(f"Markdown brief: {result.packet_markdown}")
        print(f"JSON brief: {result.packet_json}")
        print(f"Digest text: {result.digest_text}")
        print(f"Digest sent: {'yes' if result.digest_sent else 'no'}")
        return 0

    if args.command == "list-targets":
        repo = _repo_for_workspace(Path(args.workspace))
        for target in repo.list_targets():
            print(
                f"{target.id}\t{target.kind}\t{target.status}\t{target.name}\t{target.source}\t{target.url or '-'}"
            )
        return 0

    if args.command == "mark-status":
        repo = _repo_for_workspace(Path(args.workspace))
        repo.update_status(
            args.target_id,
            status=args.status,
            followup_date=args.followup_date,
            reason=args.reason,
        )
        print(f"Updated target {args.target_id} -> {args.status}")
        return 0

    if args.command == "feedback-summary":
        repo = _repo_for_workspace(Path(args.workspace))
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
        config = load_workspace_config(workspace)
        packet_dir = config.outbox_dir / args.date
        digest_path = packet_dir / "daily-digest.txt"
        json_path = packet_dir / "daily-brief.json"
        if not digest_path.exists():
            raise SystemExit(f"Missing digest file: {digest_path}")
        if not json_path.exists():
            raise SystemExit(f"Missing packet JSON: {json_path}")
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        subject = _email_subject_from_packet_payload(args.date, payload)
        send_email_digest(
            email_config=config.email,
            subject=subject,
            body=digest_path.read_text(encoding="utf-8"),
        )
        print(f"Sent digest for {args.date}")
        print(f"Digest file: {digest_path}")
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
    initialize_workspace(workspace)
    config = load_workspace_config(workspace)
    initialize_database(config.database_path)
    return Repository(connect(config.database_path))


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


def _email_subject_from_packet_payload(packet_date: str, payload: dict[str, object]) -> str:
    return render_email_subject(
        packet_date,
        new_items=[None] * len(payload.get("new_targets", [])),
        followup_items=[None] * len(payload.get("followups_due", [])),
    )


def _add_launchd_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", required=True, help="Workspace path.")
    parser.add_argument("--label", default=DEFAULT_LABEL, help="Launchd label.")
    parser.add_argument("--hour", type=int, default=8, help="Hour in local time.")
    parser.add_argument("--minute", type=int, default=0, help="Minute in local time.")
    parser.add_argument(
        "--discover-track",
        action="append",
        default=["connectors", "founders"],
        choices=sorted(TRACKS),
        help="Built-in discovery track(s) to run before the packet.",
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
    repo_root = Path(__file__).resolve().parents[2]
    logs_dir = workspace / "var" / "log"
    label = str(args.label).strip() or DEFAULT_LABEL
    return LaunchdSpec(
        label=label,
        plist_path=default_launch_agent_path(label),
        hour=int(args.hour),
        minute=int(args.minute),
        program_arguments=build_program_arguments(
            repo_root=repo_root,
            workspace=workspace,
            discover_tracks=list(args.discover_track),
            discover_per_query_limit=args.discover_per_query_limit,
            send_digest=not args.no_send_digest,
        ),
        working_directory=repo_root,
        stdout_path=logs_dir / "launchd.stdout.log",
        stderr_path=logs_dir / "launchd.stderr.log",
    )
