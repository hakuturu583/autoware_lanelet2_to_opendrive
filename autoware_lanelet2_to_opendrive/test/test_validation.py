"""Tests for OpenDRIVE validation functionality."""

from autoware_lanelet2_to_opendrive.opendrive.lane import Lane
from autoware_lanelet2_to_opendrive.opendrive.lane_elements import LaneLink
from autoware_lanelet2_to_opendrive.opendrive.lane_section import LaneSection
from autoware_lanelet2_to_opendrive.opendrive.lane_sections import Lanes
from autoware_lanelet2_to_opendrive.opendrive.opendrive_dataclass import LaneType
from autoware_lanelet2_to_opendrive.opendrive.road import Road
from autoware_lanelet2_to_opendrive.opendrive.road_links import (
    Predecessor,
    RoadLink,
    Successor,
)
from autoware_lanelet2_to_opendrive.opendrive.enums import ContactPoint, ElementType
from autoware_lanelet2_to_opendrive.opendrive.validation import (
    ASYMMETRY_FOREIGN_JUNCTION,
    ASYMMETRY_MISSING,
    ASYMMETRY_OTHER_ROAD,
    validate_lane_road_link_consistency,
    validate_road_link_symmetry,
)


def create_test_lane(
    lane_id: int,
    has_predecessor: bool = False,
    has_successor: bool = False,
) -> Lane:
    """Create a test lane with optional predecessor/successor."""
    lane = Lane(
        lane_id=lane_id,
        lane_type=LaneType.DRIVING,
        level=False,
    )

    if has_predecessor:
        lane.predecessor = LaneLink(id=lane_id)

    if has_successor:
        lane.successor = LaneLink(id=lane_id)

    return lane


def create_test_road(
    road_id: int,
    has_road_predecessor: bool = False,
    has_road_successor: bool = False,
    junction: int = -1,
) -> Road:
    """Create a test road with optional road-level predecessor/successor."""
    # Create road link if needed
    road_link = None
    if has_road_predecessor or has_road_successor:
        predecessor = None
        successor = None

        if has_road_predecessor:
            predecessor = Predecessor(
                element_type=ElementType.ROAD,
                element_id=road_id - 1,
                contact_point=ContactPoint.END,
            )

        if has_road_successor:
            successor = Successor(
                element_type=ElementType.ROAD,
                element_id=road_id + 1,
                contact_point=ContactPoint.START,
            )

        road_link = RoadLink(predecessor=predecessor, successor=successor)

    # Create lane section with test lanes
    lane_section = LaneSection(s_offset=0.0)

    # Create lanes sections
    lanes = Lanes(lane_sections=[lane_section])

    # Create road
    road = Road(
        id=road_id,
        name=f"test_road_{road_id}",
        length=100.0,
        junction=junction,
        link=road_link,
        lanes=lanes,
    )

    return road


class TestLaneRoadLinkConsistency:
    """Test suite for lane-road link consistency validation."""

    def test_valid_road_with_no_connections(self):
        """Test that a road with no lane or road connections is valid."""
        road = create_test_road(
            road_id=1, has_road_predecessor=False, has_road_successor=False
        )

        # Add lane without connections
        lane = create_test_lane(lane_id=-1, has_predecessor=False, has_successor=False)
        road.lanes.lane_sections[0].right_lanes = {-1: lane}

        result = validate_lane_road_link_consistency([road])

        assert result.is_valid
        assert result.error_count == 0

    def test_valid_road_with_consistent_connections(self):
        """Test that a road with consistent lane and road connections is valid."""
        road = create_test_road(
            road_id=1, has_road_predecessor=True, has_road_successor=True
        )

        # Add lane with connections (matches road connections)
        lane = create_test_lane(lane_id=-1, has_predecessor=True, has_successor=True)
        road.lanes.lane_sections[0].right_lanes = {-1: lane}

        result = validate_lane_road_link_consistency([road])

        assert result.is_valid
        assert result.error_count == 0

    def test_invalid_lane_predecessor_without_road_predecessor(self):
        """Test that lane predecessor without road predecessor is invalid."""
        road = create_test_road(
            road_id=1, has_road_predecessor=False, has_road_successor=True
        )

        # Add lane with predecessor but road has no predecessor
        lane = create_test_lane(lane_id=-1, has_predecessor=True, has_successor=True)
        road.lanes.lane_sections[0].right_lanes = {-1: lane}

        result = validate_lane_road_link_consistency([road])

        assert not result.is_valid
        assert result.error_count == 1
        assert result.errors[0].road_id == 1
        assert result.errors[0].lane_id == -1
        assert result.errors[0].connection_type == "predecessor"
        assert "Lane has predecessor but road does not" in result.errors[0].message

    def test_invalid_lane_successor_without_road_successor(self):
        """Test that lane successor without road successor is invalid."""
        road = create_test_road(
            road_id=1, has_road_predecessor=True, has_road_successor=False
        )

        # Add lane with successor but road has no successor
        lane = create_test_lane(lane_id=-1, has_predecessor=True, has_successor=True)
        road.lanes.lane_sections[0].right_lanes = {-1: lane}

        result = validate_lane_road_link_consistency([road])

        assert not result.is_valid
        assert result.error_count == 1
        assert result.errors[0].road_id == 1
        assert result.errors[0].lane_id == -1
        assert result.errors[0].connection_type == "successor"
        assert "Lane has successor but road does not" in result.errors[0].message

    def test_invalid_multiple_lanes_with_invalid_connections(self):
        """Test that multiple lanes with invalid connections are detected."""
        road = create_test_road(
            road_id=1, has_road_predecessor=False, has_road_successor=False
        )

        # Add multiple lanes with invalid connections
        lane1 = create_test_lane(lane_id=-1, has_predecessor=True, has_successor=True)
        lane2 = create_test_lane(lane_id=-2, has_predecessor=True, has_successor=False)

        road.lanes.lane_sections[0].right_lanes = {-1: lane1, -2: lane2}

        result = validate_lane_road_link_consistency([road])

        assert not result.is_valid
        assert result.error_count == 3  # lane1 pred, lane1 succ, lane2 pred

    def test_connecting_road_requires_road_links_for_lane_links(self):
        """Test that connecting roads also require road links before lane links.

        Previous behavior allowed connecting roads to have lane links without road links,
        but this violated OpenDRIVE specification and caused issues. Connecting roads
        must also have road-level links before lane-level links can be created.
        """
        # Create connecting road (junction member)
        road = create_test_road(
            road_id=1,
            has_road_predecessor=False,
            has_road_successor=False,
            junction=100,  # Member of junction 100
        )

        # Add lane with connections (should NOT be allowed even for connecting roads)
        lane = create_test_lane(lane_id=-1, has_predecessor=True, has_successor=True)
        road.lanes.lane_sections[0].right_lanes = {-1: lane}

        result = validate_lane_road_link_consistency([road])

        # Connecting roads must also have consistent road/lane links
        assert not result.is_valid
        assert result.error_count == 2  # predecessor and successor both invalid

    def test_validation_result_error_summary(self):
        """Test that ValidationResult provides useful error summary."""
        road = create_test_road(
            road_id=1, has_road_predecessor=False, has_road_successor=False
        )

        lane = create_test_lane(lane_id=-1, has_predecessor=True, has_successor=False)
        road.lanes.lane_sections[0].right_lanes = {-1: lane}

        result = validate_lane_road_link_consistency([road])

        summary = result.get_error_summary()

        assert "Found 1 validation errors" in summary
        assert "Road 1 Lane -1" in summary
        assert "predecessor" in summary

    def test_empty_roads_list(self):
        """Test validation with empty roads list."""
        result = validate_lane_road_link_consistency([])

        assert result.is_valid
        assert result.error_count == 0

    def test_road_without_lanes(self):
        """Test validation with road that has no lanes."""
        road = Road(
            id=1,
            name="test_road_1",
            length=100.0,
            junction=-1,
            link=None,
            lanes=None,
        )

        result = validate_lane_road_link_consistency([road])

        assert result.is_valid
        assert result.error_count == 0


# ---------------------------------------------------------------------------
# Road link symmetry (issue #68)
# ---------------------------------------------------------------------------


def _linked_road(
    road_id: int,
    *,
    predecessor: "tuple[ElementType, int] | None" = None,
    successor: "tuple[ElementType, int] | None" = None,
    junction: int = -1,
) -> Road:
    """Return a road stating the links given, and nothing else."""
    link = RoadLink()
    if predecessor is not None:
        element_type, element_id = predecessor
        link.predecessor = Predecessor(
            element_type=element_type,
            element_id=element_id,
            contact_point=(
                ContactPoint.END if element_type is ElementType.ROAD else None
            ),
        )
    if successor is not None:
        element_type, element_id = successor
        link.successor = Successor(
            element_type=element_type,
            element_id=element_id,
            contact_point=(
                ContactPoint.START if element_type is ElementType.ROAD else None
            ),
        )
    return Road(
        id=road_id,
        name=f"test_road_{road_id}",
        length=100.0,
        junction=junction,
        link=link,
        lanes=None,
    )


class TestRoadLinkSymmetry:
    """A link is a claim about a shared boundary, and both roads must make it.

    A consumer walks the network from whichever road it happens to start on,
    so a link only one of the two states is a topology that depends on the
    direction of travel.
    """

    def test_a_link_both_roads_state_is_not_reported(self) -> None:
        roads = [
            _linked_road(1, successor=(ElementType.ROAD, 2)),
            _linked_road(2, predecessor=(ElementType.ROAD, 1)),
        ]

        report = validate_road_link_symmetry(roads)

        assert report.is_valid
        assert report.road_link_count == 2
        assert "agree at both ends" in report.get_error_summary()

    def test_the_standard_junction_idiom_is_not_reported(self) -> None:
        """A road adjoining a junction names the junction, not the road beyond.

        This is how OpenDRIVE is written, so counting it as a fault would bury
        the real ones -- on the project's fixture it is the large majority of
        one-sided links.
        """
        roads = [
            _linked_road(1, successor=(ElementType.ROAD, 2), junction=7),
            _linked_road(2, predecessor=(ElementType.JUNCTION, 7)),
        ]

        report = validate_road_link_symmetry(roads, {7: {1}})

        assert report.is_valid

    def test_a_junction_that_does_not_list_the_road_is_reported(self) -> None:
        """The same shape, minus the thing that made it legitimate."""
        roads = [
            _linked_road(1, successor=(ElementType.ROAD, 2)),
            _linked_road(2, predecessor=(ElementType.JUNCTION, 7)),
        ]

        report = validate_road_link_symmetry(roads, {7: {3, 4}})

        assert not report.is_valid
        (found,) = report.asymmetries
        assert found.road_id == 1
        assert found.side == "successor"
        assert found.kind == ASYMMETRY_FOREIGN_JUNCTION

    def test_two_roads_claiming_one_end_of_a_third_is_reported(self) -> None:
        """A merge, which one predecessor slot cannot hold.

        Roads 1 and 3 both run into road 2.  OpenDRIVE gives road 2 a single
        predecessor, so whichever is written second replaces the first and the
        other claim is left stating something the map no longer agrees with.
        The boundary needs a junction to hold both.
        """
        roads = [
            _linked_road(1, successor=(ElementType.ROAD, 2)),
            _linked_road(2, predecessor=(ElementType.ROAD, 3)),
            _linked_road(3, successor=(ElementType.ROAD, 2)),
        ]

        report = validate_road_link_symmetry(roads)

        reported = {(a.road_id, a.kind) for a in report.asymmetries}
        assert (1, ASYMMETRY_OTHER_ROAD) in reported

    def test_a_far_road_stating_nothing_is_reported(self) -> None:
        roads = [
            _linked_road(1, successor=(ElementType.ROAD, 2)),
            _linked_road(2),
        ]

        report = validate_road_link_symmetry(roads)

        (found,) = report.asymmetries
        assert found.kind == ASYMMETRY_MISSING

    def test_a_link_naming_a_road_that_is_not_there_is_reported(self) -> None:
        """A dangling id is the same fault as a contradicted one."""
        report = validate_road_link_symmetry(
            [_linked_road(1, successor=(ElementType.ROAD, 99))]
        )

        (found,) = report.asymmetries
        assert found.other_road_id == 99
        assert found.kind == ASYMMETRY_MISSING

    def test_a_junction_link_is_not_itself_a_road_link(self) -> None:
        """Only road-to-road claims are counted, so the denominator means
        something."""
        roads = [
            _linked_road(1, successor=(ElementType.JUNCTION, 7)),
            _linked_road(2, predecessor=(ElementType.JUNCTION, 7)),
        ]

        report = validate_road_link_symmetry(roads)

        assert report.road_link_count == 0
        assert report.is_valid

    def test_the_summary_groups_by_shape_and_names_the_roads(self) -> None:
        """The summary is read in a conversion log, so it has to say which
        roads to look at without printing every one of them."""
        roads = [
            _linked_road(1, successor=(ElementType.ROAD, 2)),
            _linked_road(2, predecessor=(ElementType.ROAD, 3)),
            _linked_road(3, successor=(ElementType.ROAD, 2)),
        ]

        summary = validate_road_link_symmetry(roads).get_error_summary()

        assert "road 1 successor 2" in summary
        assert ASYMMETRY_OTHER_ROAD in summary
