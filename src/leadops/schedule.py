from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import plistlib
import subprocess


DEFAULT_LABEL = "com.choey.leadops.daily"


@dataclass(frozen=True, slots=True)
class LaunchdSpec:
    label: str
    plist_path: Path
    hour: int
    minute: int
    program_arguments: list[str]
    working_directory: Path
    stdout_path: Path
    stderr_path: Path


def default_launch_agent_path(label: str) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"


def build_program_arguments(
    *,
    repo_root: Path,
    workspace: Path,
    discover_tracks: list[str],
    discover_per_query_limit: int | None,
    send_digest: bool,
) -> list[str]:
    args = [str(repo_root / "bin" / "leadops-daily"), str(workspace)]
    for track in discover_tracks:
        args.extend(["--discover-track", track])
    if discover_per_query_limit is not None:
        args.extend(["--discover-per-query-limit", str(discover_per_query_limit)])
    if send_digest:
        args.append("--send-digest")
    return args


def render_launchd_plist(spec: LaunchdSpec) -> str:
    payload = {
        "Label": spec.label,
        "ProgramArguments": spec.program_arguments,
        "WorkingDirectory": str(spec.working_directory),
        "RunAtLoad": False,
        "StartCalendarInterval": {
            "Hour": spec.hour,
            "Minute": spec.minute,
        },
        "StandardOutPath": str(spec.stdout_path),
        "StandardErrorPath": str(spec.stderr_path),
    }
    return plistlib.dumps(payload, sort_keys=False).decode("utf-8")


def install_launchd_spec(spec: LaunchdSpec, *, load: bool = True) -> None:
    spec.plist_path.parent.mkdir(parents=True, exist_ok=True)
    spec.stdout_path.parent.mkdir(parents=True, exist_ok=True)
    spec.stderr_path.parent.mkdir(parents=True, exist_ok=True)
    spec.plist_path.write_text(render_launchd_plist(spec), encoding="utf-8")

    if not load:
        return

    domain = f"gui/{os.getuid()}"
    subprocess.run(
        ["launchctl", "bootout", domain, str(spec.plist_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["launchctl", "bootstrap", domain, str(spec.plist_path)],
        check=True,
        capture_output=True,
        text=True,
    )
