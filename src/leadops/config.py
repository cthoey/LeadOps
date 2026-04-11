from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex
import tomllib


DEFAULT_CONFIG = """\
[profile]
name = "Your Practice"
offer = "Independent product engineer helping founders and small product teams turn ideas, roadmaps, and rough prototypes into real customer-facing software."
ideal_customer = "Founders and small product teams with direct access to a real decision-maker and a real product initiative that needs one accountable builder."
fit_definition = "Prefer project-shaped engagements where one external builder can help shape scope, make core technical decisions, build, launch, and hand off. Existing products are still a fit when there is a meaningful implementation transition, build gap, or ownership gap."
preferred_signals = [
  "direct decision-maker is visible",
  "roadmap, prototype, or rough product needs implementation",
  "project-shaped build or milestone language",
  "design-to-build handoff or implementation transition",
  "launch pressure or explicit push toward shipping",
  "small team or no obvious internal engineering owner for this slice",
  "existing product with a meaningful implementation or ownership gap"
]
caution_signals = [
  "hiring or staff augmentation framing",
  "fractional CTO or advisory-only ask",
  "maintenance, rescue, or cleanup as the main work",
  "mature engineering org or many existing stakeholders",
  "strong inherited technical constraints with little scope-shaping room",
  "vague thread with little public evidence"
]
post_contact_checks = [
  "budget and commercial scope",
  "real authority and decision path",
  "sponsor quality and handoff owner",
  "constraints around any existing prototype or production system",
  "delivery viability and internal ability to absorb the work"
]
daily_new_lead_cap = 5
daily_followup_cap = 5
cooldown_days = 21
hard_rejects = [
  "employment-style work",
  "staff augmentation",
  "fractional CTO work",
  "maintenance-heavy work",
  "rescue-only work",
  "mature companies with established engineering teams"
]

[llm]
provider = "mock"
# provider = "command"
# Recommended first live setup:
# command = "python3 -m leadops.openai_bridge --model gpt-5.4 --reasoning-effort high --max-output-tokens 4000"
timeout_seconds = 90

[discovery]
provider = "none"
# provider = "command"
# Recommended first live setup:
# command = "python3 -m leadops.openai_discover --model gpt-5.4 --reasoning-effort low --max-output-tokens 5000"
timeout_seconds = 180

[email]
mode = "none"
# mode = "smtp"
# host = "smtp.example.com"
# port = 587
# username = "you@example.com"
# password_env = "LEADOPS_SMTP_PASSWORD"
# from_addr = "you@example.com"
# to_addr = "you@example.com"
# starttls = true
# send_on_run = false
"""


@dataclass(slots=True)
class ProfileConfig:
    name: str
    offer: str
    ideal_customer: str
    fit_definition: str
    preferred_signals: list[str]
    caution_signals: list[str]
    post_contact_checks: list[str]
    hard_rejects: list[str]
    daily_new_lead_cap: int
    daily_followup_cap: int
    cooldown_days: int


@dataclass(slots=True)
class LLMConfig:
    provider: str
    command: list[str]
    timeout_seconds: int


@dataclass(slots=True)
class DiscoveryConfig:
    provider: str
    command: list[str]
    timeout_seconds: int


@dataclass(slots=True)
class EmailConfig:
    mode: str
    host: str
    port: int
    username: str
    password_env: str
    from_addr: str
    to_addr: str
    starttls: bool
    send_on_run: bool


@dataclass(slots=True)
class WorkspaceConfig:
    root: Path
    profile: ProfileConfig
    llm: LLMConfig
    discovery: DiscoveryConfig
    email: EmailConfig

    @property
    def database_path(self) -> Path:
        return self.root / "var" / "leadops.db"

    @property
    def outbox_dir(self) -> Path:
        return self.root / "outbox"


def config_path(workspace: Path) -> Path:
    return workspace / "leadops.toml"


def load_workspace_config(workspace: Path) -> WorkspaceConfig:
    workspace = workspace.expanduser().resolve()
    path = config_path(workspace)
    if not path.exists():
        raise FileNotFoundError(f"Missing workspace config: {path}")

    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    profile_raw = payload.get("profile", {})
    llm_raw = payload.get("llm", {})
    discovery_raw = payload.get("discovery", {})
    email_raw = payload.get("email", {})
    command_text = str(llm_raw.get("command", "")).strip()
    discovery_command_text = str(discovery_raw.get("command", "")).strip()

    profile = ProfileConfig(
        name=str(profile_raw.get("name", "Your Practice")),
        offer=str(profile_raw.get("offer", "")).strip(),
        ideal_customer=str(profile_raw.get("ideal_customer", "")).strip(),
        fit_definition=str(profile_raw.get("fit_definition", "")).strip(),
        preferred_signals=[str(item) for item in profile_raw.get("preferred_signals", [])],
        caution_signals=[str(item) for item in profile_raw.get("caution_signals", [])],
        post_contact_checks=[str(item) for item in profile_raw.get("post_contact_checks", [])],
        hard_rejects=[str(item) for item in profile_raw.get("hard_rejects", [])],
        daily_new_lead_cap=int(profile_raw.get("daily_new_lead_cap", 5)),
        daily_followup_cap=int(profile_raw.get("daily_followup_cap", 5)),
        cooldown_days=int(profile_raw.get("cooldown_days", 21)),
    )
    llm = LLMConfig(
        provider=str(llm_raw.get("provider", "mock")).strip() or "mock",
        command=shlex.split(command_text) if command_text else [],
        timeout_seconds=int(llm_raw.get("timeout_seconds", 90)),
    )
    discovery = DiscoveryConfig(
        provider=str(discovery_raw.get("provider", "none")).strip() or "none",
        command=shlex.split(discovery_command_text) if discovery_command_text else [],
        timeout_seconds=int(discovery_raw.get("timeout_seconds", 180)),
    )
    email = EmailConfig(
        mode=str(email_raw.get("mode", "none")).strip() or "none",
        host=str(email_raw.get("host", "")).strip(),
        port=int(email_raw.get("port", 587)),
        username=str(email_raw.get("username", "")).strip(),
        password_env=str(email_raw.get("password_env", "LEADOPS_SMTP_PASSWORD")).strip()
        or "LEADOPS_SMTP_PASSWORD",
        from_addr=str(email_raw.get("from_addr", "")).strip(),
        to_addr=str(email_raw.get("to_addr", "")).strip(),
        starttls=bool(email_raw.get("starttls", True)),
        send_on_run=bool(email_raw.get("send_on_run", False)),
    )
    return WorkspaceConfig(root=workspace, profile=profile, llm=llm, discovery=discovery, email=email)


def initialize_workspace(workspace: Path) -> Path:
    workspace = workspace.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    for relative in ("var", "outbox", "inbox", "cache"):
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    path = config_path(workspace)
    if not path.exists():
        path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    return workspace
