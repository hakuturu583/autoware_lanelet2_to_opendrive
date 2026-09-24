"""The snapped heading comes from the frame the pose was given in.

A Lanelet2 pose keeps its lanelet's direction of travel; an OpenDRIVE pose
keeps the road's. The distinction matters on a left-hand-traffic map converted
from Lanelet2, where the two disagree by about 180 degrees and an ego snapped
to the wrong one spawns facing back down its lane.

The CARLA world and the coordinate transforms are stood in for, so these run
without a server or a loaded map.
"""

from __future__ import annotations

import pytest

from autoware_carla_scenario.coordinate import snap as snap_module
from autoware_carla_scenario.coordinate.poses import (
    CarlaWorldPose,
    Lanelet2Pose,
    OpenDrivePose,
)

#: The lanelet's own direction of travel, and the reference line's -- opposed,
#: as they are on the converted Odaiba map.
_LANELET_YAW = 57.5
_REFERENCE_LINE_YAW = 238.3


class _FakeRoad:
    pass


class _FakeRoadNetwork:
    def __init__(self) -> None:
        self.road_ids_to_object = {"38": _FakeRoad()}


class _FakeMapManager:
    road_network = _FakeRoadNetwork()

    @classmethod
    def get_instance(cls) -> "_FakeMapManager":
        return cls()


@pytest.fixture
def _transforms(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stand in for the map-backed conversions the snap calls."""
    od_pose = OpenDrivePose(road_id="38", lane_id=1, s=103.0, t=0.0, heading=0.0)

    def _to_opendrive(pose):
        return od_pose

    def _to_carla_world(pose):
        # The reference line and the lanelet disagree; which one the snap picks
        # is exactly what these tests are about.
        yaw = _LANELET_YAW if isinstance(pose, Lanelet2Pose) else _REFERENCE_LINE_YAW
        return CarlaWorldPose(x=-2884.7, y=3035.4, z=6.9, yaw=yaw)

    monkeypatch.setattr(
        "autoware_carla_scenario.coordinate.transform.to_opendrive", _to_opendrive
    )
    monkeypatch.setattr(
        "autoware_carla_scenario.coordinate.transform.to_carla_world", _to_carla_world
    )
    monkeypatch.setattr(
        "autoware_carla_scenario.coordinate.transform._lane_center_t",
        lambda *_a, **_k: 0.0,
    )
    monkeypatch.setattr(
        "autoware_carla_scenario.coordinate.map_manager.MapManager", _FakeMapManager
    )
    monkeypatch.setattr(
        snap_module, "_z_from_nearest_spawn_point", lambda *_a, **_k: 6.9
    )
    monkeypatch.setattr(
        snap_module, "refine_z_with_ground_projection", lambda x, y, z, *_a, **_k: z
    )


def test_a_lanelet_pose_keeps_its_lanelets_heading(_transforms: None) -> None:
    """Snapping a Lanelet2 pose must not adopt the reference line's direction."""
    snapped = snap_module._snap_lanelet2_via_opendrive(
        Lanelet2Pose(lanelet_id=83, s=102.87),
        world=object(),  # type: ignore[arg-type]
        ground_projection=snap_module.GroundProjectionConfig(),
    )

    assert snapped.yaw == pytest.approx(_LANELET_YAW)
    # The position still comes from the OpenDRIVE round-trip, which is what
    # puts it on the surface CARLA trusts.
    assert snapped.x == pytest.approx(-2884.7)
    assert snapped.y == pytest.approx(3035.4)
