"""Validation utilities for OpenDRIVE data consistency.

This module provides validation functions to ensure OpenDRIVE files comply with the
specification and prevent issues in downstream tools like CARLA.
"""

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    pass

from .road import Road


@dataclass
class LaneConnectionError:
    """Represents an invalid lane connection error."""

    road_id: int
    lane_id: int
    connection_type: str  # "predecessor" or "successor"
    message: str


@dataclass
class ValidationResult:
    """Result of OpenDRIVE validation."""

    is_valid: bool
    errors: List[LaneConnectionError]

    @property
    def error_count(self) -> int:
        """Return the number of validation errors."""
        return len(self.errors)

    def get_error_summary(self) -> str:
        """Return a human-readable summary of validation errors."""
        if self.is_valid:
            return "No validation errors found."

        summary_lines = [
            f"Found {self.error_count} validation errors:",
            "",
        ]

        for error in self.errors:
            summary_lines.append(
                f"  Road {error.road_id} Lane {error.lane_id} "
                f"({error.connection_type}): {error.message}"
            )

        return "\n".join(summary_lines)


def validate_lane_road_link_consistency(
    roads: List[Road],
) -> ValidationResult:
    """Validate consistency between lane-level and road-level connections.

    This function checks that lane predecessor/successor links only exist when the
    corresponding road-level predecessor/successor exists. This prevents invalid
    OpenDRIVE files that cause crashes in tools like CARLA.

    Issue #202: Invalid lane connections without corresponding road connections
    cause segmentation faults in OpenDRIVE parsers.

    Args:
        roads: List of Road objects to validate

    Returns:
        ValidationResult containing validation status and any errors found

    Example:
        >>> from autoware_lanelet2_to_opendrive.opendrive.opendrive import OpenDRIVE
        >>> from autoware_lanelet2_to_opendrive.opendrive.validation import (
        ...     validate_lane_road_link_consistency
        ... )
        >>> opendrive = OpenDRIVE(roads=[...])
        >>> result = validate_lane_road_link_consistency(opendrive.roads)
        >>> if not result.is_valid:
        ...     print(result.get_error_summary())
    """
    errors: List[LaneConnectionError] = []

    for road in roads:
        # Check if road has link connections
        has_road_predecessor = (
            road.link is not None and road.link.predecessor is not None
        )
        has_road_successor = road.link is not None and road.link.successor is not None

        # Check lanes in all lane sections
        if road.lanes is None:
            continue

        for lane_section in road.lanes.lane_sections:
            # Check all lanes (left, center, right)
            all_lanes: List[Any] = []

            if lane_section.left_lanes:
                all_lanes.extend(lane_section.left_lanes.values())

            # Center lane is a single ReferenceLine, not a dict
            # Typically center lane (ID=0) doesn't have predecessor/successor
            # so we skip it for validation

            if lane_section.right_lanes:
                all_lanes.extend(lane_section.right_lanes.values())

            for lane in all_lanes:
                # Check lane predecessor
                if lane.predecessor is not None:
                    if not has_road_predecessor:
                        errors.append(
                            LaneConnectionError(
                                road_id=road.id,
                                lane_id=lane.lane_id,
                                connection_type="predecessor",
                                message=(
                                    "Lane has predecessor but road does not have "
                                    "predecessor link"
                                ),
                            )
                        )

                # Check lane successor
                if lane.successor is not None:
                    if not has_road_successor:
                        errors.append(
                            LaneConnectionError(
                                road_id=road.id,
                                lane_id=lane.lane_id,
                                connection_type="successor",
                                message=(
                                    "Lane has successor but road does not have "
                                    "successor link"
                                ),
                            )
                        )

    return ValidationResult(is_valid=(len(errors) == 0), errors=errors)


def validate_no_duplicate_road_ids(roads: List[Road]) -> ValidationResult:
    """Validate that no two roads share the same ID.

    Duplicate road IDs can cause silent data corruption when building lookup
    dictionaries (last writer wins) and lead to invalid lane links or dangling
    road references in the output OpenDRIVE file.

    Args:
        roads: List of Road objects to validate

    Returns:
        ValidationResult containing validation status and any errors found

    Example:
        >>> result = validate_no_duplicate_road_ids(all_roads)
        >>> if not result.is_valid:
        ...     print(result.get_error_summary())
    """
    errors: List[LaneConnectionError] = []

    id_counts = Counter(road.id for road in roads)
    for road_id, count in id_counts.items():
        if count > 1:
            errors.append(
                LaneConnectionError(
                    road_id=road_id,
                    lane_id=0,
                    connection_type="duplicate",
                    message=f"Road ID {road_id} appears {count} times in the road list",
                )
            )

    return ValidationResult(is_valid=(len(errors) == 0), errors=errors)


@dataclass
class RoadLinkAsymmetry:
    """One road-to-road link that the road at the far end does not agree with.

    Attributes:
        road_id: The road that states the link.
        side: ``predecessor`` or ``successor`` -- the end it states it on.
        other_road_id: The road it names.
        kind: Which shape the disagreement takes; see
            :func:`validate_road_link_symmetry`.
        message: What the far road says instead, phrased for someone reading
            the conversion log.
    """

    road_id: int
    side: str
    other_road_id: int
    kind: str
    message: str


@dataclass
class RoadLinkReport:
    """The one-sided road links found in a converted map."""

    asymmetries: List[RoadLinkAsymmetry]
    road_link_count: int

    @property
    def is_valid(self) -> bool:
        """Whether every road-to-road link is agreed at both ends."""
        return not self.asymmetries

    def get_error_summary(self) -> str:
        """Return a human-readable summary, grouped by shape."""
        if self.is_valid:
            return f"All {self.road_link_count} road-to-road links agree at both ends."

        by_kind: "dict[str, List[RoadLinkAsymmetry]]" = {}
        for item in self.asymmetries:
            by_kind.setdefault(item.kind, []).append(item)

        lines = [
            f"{len(self.asymmetries)} of {self.road_link_count} road-to-road "
            "links are stated by one road and not agreed by the other:",
            "",
        ]
        for kind in sorted(by_kind):
            found = by_kind[kind]
            lines.append(f"  {len(found)} x {kind}")
            for item in found[:5]:
                lines.append(
                    f"      road {item.road_id} {item.side} {item.other_road_id}: "
                    f"{item.message}"
                )
            if len(found) > 5:
                lines.append(f"      ... and {len(found) - 5} more")
        return "\n".join(lines)


#: A link the far road does not mention at all.
ASYMMETRY_MISSING = "the far road states no link on that end"
#: Two roads claim the same end of a third, and only one fits in the slot.
ASYMMETRY_OTHER_ROAD = "the far road names a different road"
#: The far road names a junction that this road is not a connecting road of.
ASYMMETRY_FOREIGN_JUNCTION = "the far road names a junction this road is not in"


def validate_road_link_symmetry(
    roads: List[Road],
    junction_road_ids: "dict[int, set[int]] | None" = None,
) -> RoadLinkReport:
    """Return the road-to-road links only one of the two roads agrees with.

    A road-to-road link is a claim about a shared boundary, and both roads
    have to make it for a consumer walking the network to read the same
    topology from either end.

    **A link written from one side only is usually correct**, and is not
    reported.  OpenDRIVE has a road adjoining a junction name the *junction*
    rather than the connecting road beyond it, so ``A.successor = B`` sitting
    opposite ``B.predecessor = junction 7`` is the standard idiom whenever A
    is one of that junction's roads.  Only the links that no idiom explains
    are returned, under one of three kinds:

    * :data:`ASYMMETRY_MISSING` -- the far road says nothing on that end.
    * :data:`ASYMMETRY_OTHER_ROAD` -- it names a different road.  Two roads
      claim the same end of a third, which is a merge: OpenDRIVE gives a road
      one predecessor and one successor, so the second claim has nowhere to go
      and the shared boundary needs a junction to hold both.
    * :data:`ASYMMETRY_FOREIGN_JUNCTION` -- it names a junction this road is
      not part of, which is the same merge seen from the other side: a
      junction took the slot and the road link was left stating something the
      map no longer agrees with.

    Args:
        roads: Every road in the converted map.
        junction_road_ids: Junction id to the ids of the roads it connects,
            used to recognise the idiom above.  Without it every junction
            named opposite a road link is treated as foreign, so pass it
            whenever the junctions are to hand.

    Returns:
        A :class:`RoadLinkReport`.
    """
    junction_road_ids = junction_road_ids or {}
    by_id = {road.id: road for road in roads}

    def stated(road: "Road | None", side: str) -> "tuple[str, int] | None":
        """Return ``(element_type, element_id)`` stated on *side*, or None."""
        if road is None or road.link is None:
            return None
        element = getattr(road.link, side, None)
        if element is None:
            return None
        return element.element_type.value, int(element.element_id)

    asymmetries: List[RoadLinkAsymmetry] = []
    link_count = 0

    for road in roads:
        for side, far_side in (
            ("successor", "predecessor"),
            ("predecessor", "successor"),
        ):
            claim = stated(road, side)
            if claim is None or claim[0] != "road":
                continue
            link_count += 1
            other_id = claim[1]
            far = stated(by_id.get(other_id), far_side)

            if far is None:
                kind, message = ASYMMETRY_MISSING, "it states no link there"
            elif far[0] == "road" and far[1] == road.id:
                continue  # agreed at both ends
            elif far[0] == "road":
                kind = ASYMMETRY_OTHER_ROAD
                message = f"it names road {far[1]} there instead"
            elif road.id in junction_road_ids.get(far[1], set()):
                continue  # the standard idiom: this road is in that junction
            else:
                kind = ASYMMETRY_FOREIGN_JUNCTION
                message = f"it names junction {far[1]}, which does not list this road"

            asymmetries.append(
                RoadLinkAsymmetry(
                    road_id=road.id,
                    side=side,
                    other_road_id=other_id,
                    kind=kind,
                    message=message,
                )
            )

    return RoadLinkReport(asymmetries=asymmetries, road_link_count=link_count)
