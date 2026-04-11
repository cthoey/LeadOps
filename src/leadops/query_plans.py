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


REFERRAL_PARTNER_TRACK = QueryTrack(
    name="referral_partners",
    description="Adjacent studios and consultancies that can refer scoped implementation work.",
    queries=(
        QuerySpec(
            name="product_design_handoff",
            kind="connector",
            query="product design studio official site implementation handoff small product teams",
            description="Studios that package product strategy or design work and stop before implementation.",
        ),
        QuerySpec(
            name="ux_ui_product_consultancy",
            kind="connector",
            query="UX UI agency official site small product teams software handoff",
            description="UX/UI consultancies that work upstream of engineering and may need a build partner.",
        ),
        QuerySpec(
            name="brand_web_implementation_gap",
            kind="connector",
            query="brand web studio official site product design engineering handoff",
            description="Brand or web studios that stop before implementation and may refer downstream work.",
        ),
    ),
)


DIRECT_BUYER_TRACK = QueryTrack(
    name="direct_buyers",
    description="Direct opportunities that still look close to roadmap-to-build or prototype-to-launch work.",
    queries=(
        QuerySpec(
            name="roadmap_build_transition",
            kind="founder",
            query="product roadmap prototype official site customer-facing software small team",
            description="Small teams with a real product direction who may be nearing the point of hiring one builder.",
        ),
        QuerySpec(
            name="prototype_wireframes_transition",
            kind="founder",
            query="prototype wireframes official site product team build help",
            description="Teams talking about prototypes, flows, or wireframes rather than a settled engineering organization.",
        ),
        QuerySpec(
            name="small_team_build_gap",
            kind="founder",
            query="small team no engineering team roadmap prototype official site software",
            description="Very small teams that may have product direction but no visible engineering depth.",
        ),
    ),
)


TRANSITION_SIGNAL_TRACK = QueryTrack(
    name="transition_signals",
    description="Opportunities where the public signals suggest a real implementation or ownership gap.",
    queries=(
        QuerySpec(
            name="no_code_to_custom_build",
            kind="founder",
            query="no-code prototype custom build no engineering team product team",
            description="Teams with a prototype or no-code surface that may need a real build partner.",
        ),
        QuerySpec(
            name="design_handoff_gap",
            kind="founder",
            query="product design prototype handoff no engineering team implementation",
            description="Work that may be nearing a design-to-build handoff without in-house engineering depth.",
        ),
        QuerySpec(
            name="roadmap_build_help",
            kind="founder",
            query="roadmap prototype build help project based customer-facing software",
            description="Teams whose public language suggests roadmap or prototype work that still needs a real builder.",
        ),
    ),
)


PUBLIC_SIGNAL_TRACK = QueryTrack(
    name="public_signals",
    description="Specific public surfaces where people sometimes signal explicit or unusually visible build needs.",
    queries=(
        QuerySpec(
            name="hn_freelancer_thread",
            kind="founder",
            query='site:news.ycombinator.com "Freelancer? Seeking freelancer?" "looking for developer" product build',
            description="Recurring HN freelancer threads that occasionally contain scoped builder-shaped asks.",
        ),
        QuerySpec(
            name="weweb_jobs_collabs",
            kind="founder",
            query='site:community.weweb.io/c/jobs "product" developer build project based',
            description="WeWeb jobs and collaboration posts where teams sometimes ask for real implementation help.",
        ),
        QuerySpec(
            name="bubble_jobs_freelance",
            kind="founder",
            query='site:forum.bubble.io/c/jobs-freelance product developer build project based',
            description="Bubble jobs and freelance posts where teams sometimes need a proper build partner.",
        ),
    ),
)


DAILY_TRACK = QueryTrack(
    name="daily",
    description="A compact mixed track for one daily pass.",
    queries=(
        REFERRAL_PARTNER_TRACK.queries[0],
        TRANSITION_SIGNAL_TRACK.queries[0],
        TRANSITION_SIGNAL_TRACK.queries[2],
    ),
)


TRACKS: dict[str, QueryTrack] = {
    REFERRAL_PARTNER_TRACK.name: REFERRAL_PARTNER_TRACK,
    DIRECT_BUYER_TRACK.name: DIRECT_BUYER_TRACK,
    TRANSITION_SIGNAL_TRACK.name: TRANSITION_SIGNAL_TRACK,
    PUBLIC_SIGNAL_TRACK.name: PUBLIC_SIGNAL_TRACK,
    DAILY_TRACK.name: DAILY_TRACK,
}


def get_track(name: str) -> QueryTrack:
    try:
        return TRACKS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown track: {name}") from exc


def list_tracks() -> list[QueryTrack]:
    return [
        TRACKS["referral_partners"],
        TRACKS["direct_buyers"],
        TRACKS["transition_signals"],
        TRACKS["public_signals"],
        TRACKS["daily"],
    ]
