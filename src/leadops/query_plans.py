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
    description="Founder-side opportunities that still look close to roadmap-to-build or prototype-to-launch work.",
    queries=(
        QuerySpec(
            name="roadmap_build_transition",
            kind="founder",
            query="founder roadmap prototype official site customer-facing product startup",
            description="Founders with a real product direction who may be nearing the point of hiring one builder.",
        ),
        QuerySpec(
            name="prototype_wireframes_transition",
            kind="founder",
            query="founder prototype wireframes official site product startup build",
            description="Founders talking about prototypes, flows, or wireframes rather than a settled engineering team.",
        ),
        QuerySpec(
            name="small_team_build_gap",
            kind="founder",
            query="founder no engineering team roadmap prototype official site startup",
            description="Very small teams that may have product direction but no visible engineering depth.",
        ),
    ),
)


BUILDER_NEED_TRACK = QueryTrack(
    name="builder_need",
    description="Founder-side opportunities where the public signals suggest a real implementation gap, not just an existing product.",
    queries=(
        QuerySpec(
            name="no_code_to_custom_build",
            kind="founder",
            query="founder no-code prototype custom build no engineering team startup",
            description="Founders who look like they have a prototype or no-code surface but may need a real build partner.",
        ),
        QuerySpec(
            name="design_handoff_gap",
            kind="founder",
            query="founder product design prototype handoff no engineering team startup",
            description="Founder-side work that may be nearing a design-to-build handoff without in-house engineering depth.",
        ),
        QuerySpec(
            name="roadmap_build_help",
            kind="founder",
            query="founder roadmap prototype build help project based startup",
            description="Founders whose public language suggests roadmap or prototype work that still needs a real builder.",
        ),
    ),
)


PLACE_WATCH_TRACK = QueryTrack(
    name="place_watch",
    description="Specific public surfaces where founders sometimes signal explicit or unusually visible build needs.",
    queries=(
        QuerySpec(
            name="hn_freelancer_thread",
            kind="founder",
            query='site:news.ycombinator.com "Freelancer? Seeking freelancer?" "looking for developer" MVP founder',
            description="Recurring HN freelancer threads that occasionally contain direct builder-shaped asks.",
        ),
        QuerySpec(
            name="weweb_jobs_collabs",
            kind="founder",
            query='site:community.weweb.io/c/jobs "founder" MVP developer build',
            description="WeWeb jobs and collab posts where founders sometimes ask for real implementation help.",
        ),
        QuerySpec(
            name="bubble_jobs_freelance",
            kind="founder",
            query='site:forum.bubble.io/c/jobs-freelance founder MVP developer build',
            description="Bubble jobs and freelance posts where founders sometimes need a proper build partner.",
        ),
    ),
)


DAILY_TRACK = QueryTrack(
    name="daily",
    description="A compact mixed track for one daily pass.",
    queries=(
        CONNECTOR_TRACK.queries[0],
        BUILDER_NEED_TRACK.queries[0],
        BUILDER_NEED_TRACK.queries[2],
    ),
)


TRACKS: dict[str, QueryTrack] = {
    CONNECTOR_TRACK.name: CONNECTOR_TRACK,
    FOUNDER_TRACK.name: FOUNDER_TRACK,
    BUILDER_NEED_TRACK.name: BUILDER_NEED_TRACK,
    PLACE_WATCH_TRACK.name: PLACE_WATCH_TRACK,
    DAILY_TRACK.name: DAILY_TRACK,
}


def get_track(name: str) -> QueryTrack:
    try:
        return TRACKS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown track: {name}") from exc


def list_tracks() -> list[QueryTrack]:
    return [
        TRACKS["connectors"],
        TRACKS["founders"],
        TRACKS["builder_need"],
        TRACKS["place_watch"],
        TRACKS["daily"],
    ]
