from __future__ import annotations

from dataclasses import dataclass, field


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
    packet_kind_order: tuple[str, ...] = ("founder", "connector")
    packet_kind_caps: dict[str, int] = field(default_factory=dict)

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
            "packet_kind_order": list(self.packet_kind_order),
            "packet_kind_caps": dict(self.packet_kind_caps),
        }


EARLY_PRODUCT = ApproachSpec(
    name="early_product",
    label="Founder + Connector Mix",
    description="Balanced founder-side lane: roadmap-to-build, prototype-to-launch work, and strong founder-adjacent connectors.",
    strategy=(
        "Use a mixed search strategy. Surface founder-side opportunities that still look close to roadmap-to-build "
        "or prototype-to-launch work, plus founder-adjacent connectors. Existing products are acceptable only when "
        "the public evidence shows a real implementation transition rather than generic traction, maintenance, or hiring."
    ),
    discover_tracks=("connectors", "founders"),
    prioritize=(
        "roadmap-to-build transitions",
        "rough prototypes that need real implementation",
        "connector studios with founder trust",
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


BUILDER_NEED = ApproachSpec(
    name="builder_need",
    label="Founder Needs Builder",
    description="Narrowest direct-fit lane: look for visible evidence that one accountable builder is needed now.",
    strategy=(
        "Be harsh. Prefer founders or tiny teams with a real product idea, roadmap, or prototype where public "
        "evidence suggests paying one external builder is the next sensible step. Do not reward already-live "
        "products unless the public evidence also shows a real implementation gap, design-to-build handoff, or "
        "launch ownership need."
    ),
    discover_tracks=("builder_need", "connectors"),
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
    packet_kind_order=("founder", "connector"),
    packet_kind_caps={"founder": 2, "connector": 1},
)


PLACE_WATCH = ApproachSpec(
    name="place_watch",
    label="Public Founder Asks",
    description="Monitor specific public surfaces for explicit or unusually visible builder-shaped opportunities.",
    strategy=(
        "Search a few public places where founders sometimes openly ask for help turning a roadmap, prototype, or "
        "rough product into something real. Favor freshness and direct asks. Reject cofounder requests, hiring posts, "
        "equity-only offers, or anything that looks like a role fill instead of scoped consulting."
    ),
    discover_tracks=("place_watch",),
    prioritize=(
        "fresh public asks",
        "direct founder language",
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
    EARLY_PRODUCT.name: EARLY_PRODUCT,
    BUILDER_NEED.name: BUILDER_NEED,
    PLACE_WATCH.name: PLACE_WATCH,
}


def get_approach(name: str) -> ApproachSpec:
    try:
        return APPROACHES[name]
    except KeyError as exc:
        raise ValueError(f"Unknown approach: {name}") from exc


def list_approaches() -> list[ApproachSpec]:
    return [APPROACHES["early_product"], APPROACHES["builder_need"], APPROACHES["place_watch"]]
