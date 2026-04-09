from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QuerySpec:
    name: str
    kind: str
    query: str
    description: str
    default_limit: int = 2


@dataclass(frozen=True, slots=True)
class QueryTrack:
    name: str
    description: str
    queries: tuple[QuerySpec, ...]


CONNECTOR_TRACK = QueryTrack(
    name="connectors",
    description="Founder-adjacent design and product studios that can refer roadmap-to-build work.",
    queries=(
        QuerySpec(
            name="founder_mvp_design",
            kind="connector",
            query="startup product design studio official site founders MVP build-ready handoff",
            description="Studios that package founder MVP and build-ready handoff work.",
        ),
        QuerySpec(
            name="startup_ux_ui",
            kind="connector",
            query="startup UX UI agency official site founders early stage product MVP",
            description="Startup UX/UI agencies that work with founders before engineering.",
        ),
        QuerySpec(
            name="brand_web_handoff",
            kind="connector",
            query="startup branding web studio official site founders product design handoff engineering",
            description="Brand or web studios that stop before engineering and may need a build partner.",
        ),
    ),
)


FOUNDER_TRACK = QueryTrack(
    name="founders",
    description="Tiny teams and early products that look closer to idea/prototype-to-launch work than maintenance or hiring.",
    queries=(
        QuerySpec(
            name="beta_waitlist",
            kind="founder",
            query="startup beta waitlist official site founder product SaaS",
            description="Very early software products still signaling launch-stage motion.",
        ),
        QuerySpec(
            name="early_access_product",
            kind="founder",
            query="early access product official site founder customer-facing software startup",
            description="Customer-facing products still in early access or prototype mode.",
        ),
        QuerySpec(
            name="prototype_launch",
            kind="founder",
            query="prototype official site founder launch startup software tiny team",
            description="Teams explicitly talking about prototypes and launches.",
        ),
    ),
)


DAILY_TRACK = QueryTrack(
    name="daily",
    description="A compact mixed track for one daily pass.",
    queries=(
        CONNECTOR_TRACK.queries[0],
        CONNECTOR_TRACK.queries[1],
        FOUNDER_TRACK.queries[0],
    ),
)


TRACKS: dict[str, QueryTrack] = {
    CONNECTOR_TRACK.name: CONNECTOR_TRACK,
    FOUNDER_TRACK.name: FOUNDER_TRACK,
    DAILY_TRACK.name: DAILY_TRACK,
}


def get_track(name: str) -> QueryTrack:
    try:
        return TRACKS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown track: {name}") from exc


def list_tracks() -> list[QueryTrack]:
    return [TRACKS["connectors"], TRACKS["founders"], TRACKS["daily"]]
