from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApproachSpec:
    name: str
    label: str
    description: str
    strategy: str
    discover_tracks: tuple[str, ...]
    prioritize: tuple[str, ...]
    reject: tuple[str, ...]
    default_per_query_limit: int = 2

    def as_payload(self) -> dict[str, object]:
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "strategy": self.strategy,
            "discover_tracks": list(self.discover_tracks),
            "prioritize": list(self.prioritize),
            "reject": list(self.reject),
            "default_per_query_limit": self.default_per_query_limit,
        }


BALANCED = ApproachSpec(
    name="balanced",
    label="Balanced Mix",
    description="Balanced retrieval mix: direct buyers, implementation transitions, and strong referral partners.",
    strategy=(
        "Use a mixed search strategy. Surface direct opportunities that still look close to roadmap-to-build "
        "or prototype-to-launch work, plus adjacent referral partners. Existing products are acceptable only when "
        "the public evidence shows a real implementation transition rather than generic traction, maintenance, or hiring."
    ),
    discover_tracks=("referral_partners", "direct_buyers"),
    prioritize=(
        "roadmap-to-build transitions",
        "rough prototypes that need real implementation",
        "referral partners with downstream implementation gaps",
        "early products at a real implementation transition",
    ),
    reject=(
        "staff augmentation",
        "already-live products with no build gap",
        "maintenance-heavy work",
        "mature engineering orgs",
        "advisory-only asks",
    ),
    default_per_query_limit=2,
)


TRANSITION_FOCUS = ApproachSpec(
    name="transition_focus",
    label="Transition Focus",
    description="Narrowest direct-fit lane: look for visible evidence that one accountable builder is needed now.",
    strategy=(
        "Be harsh. Prefer small teams with a real product idea, roadmap, or prototype where public "
        "evidence suggests paying one external builder is the next sensible step. Do not reward already-live "
        "products unless the public evidence also shows a real implementation gap, design-to-build handoff, or "
        "launch ownership need."
    ),
    discover_tracks=("transition_signals", "referral_partners"),
    prioritize=(
        "real product idea, roadmap, or prototype",
        "visible build gap or handoff",
        "tiny team or solo founder",
        "no obvious engineering team",
        "launch pressure",
    ),
    reject=(
        "already-live product with no build gap",
        "hiring or staff aug asks",
        "maintenance/rescue work",
        "mature teams",
    ),
    default_per_query_limit=2,
)


PUBLIC_SIGNAL_WATCH = ApproachSpec(
    name="public_signal_watch",
    label="Public Signal Watch",
    description="Monitor specific public surfaces for explicit or unusually visible builder-shaped opportunities.",
    strategy=(
        "Search a few public places where people sometimes openly ask for help turning a roadmap, prototype, or "
        "rough product into something real. Favor freshness and direct asks. Reject cofounder requests, hiring posts, "
        "equity-only offers, or anything that looks like a role fill instead of scoped consulting."
    ),
    discover_tracks=("public_signals",),
    prioritize=(
        "fresh public asks",
        "direct buyer language",
        "scoped build help",
        "project-based or milestone-shaped work",
        "implementation ownership",
    ),
    reject=(
        "cofounder requests",
        "equity-only offers",
        "job posts",
        "vague discussion threads",
    ),
    default_per_query_limit=2,
)


APPROACHES: dict[str, ApproachSpec] = {
    BALANCED.name: BALANCED,
    TRANSITION_FOCUS.name: TRANSITION_FOCUS,
    PUBLIC_SIGNAL_WATCH.name: PUBLIC_SIGNAL_WATCH,
}


def get_approach(name: str) -> ApproachSpec:
    try:
        return APPROACHES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown approach: {name}") from exc


def list_approaches() -> list[ApproachSpec]:
    return [APPROACHES["balanced"], APPROACHES["transition_focus"], APPROACHES["public_signal_watch"]]
