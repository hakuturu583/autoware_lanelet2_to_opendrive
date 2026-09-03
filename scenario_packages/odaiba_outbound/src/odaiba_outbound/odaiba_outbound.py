"""OdaibaOutboundScenario -- verify the ego reaches its goal.

This module lives in a separate installable package, not inside
``autoware_carla_scenario``.  It only depends on the framework's public API.

The Odaiba map is loaded as a lanelet2-only map (no OpenDRIVE), so the pass
condition is expressed purely in Lanelet2 coordinates: a rectangular box around
the goal centerline point, checked with :class:`EntityInAreaCondition` (which
converts its Lanelet2 vertices straight to CARLA world coordinates -- no
OpenDRIVE road network required).

Note: importing this module pulls in :class:`BaseScenario`, which imports CARLA
at module scope, so it requires the framework's runtime environment.  The
package ``__init__`` imports it lazily (inside ``register()``).  The CARLA world
itself is only touched inside :meth:`setup`, which runs on the live server.
"""

from __future__ import annotations

import logging

from autoware_carla_scenario import (
    EGO_ROLE_NAME,
    BaseScenario,
    EgoConfig,
    EntityInAreaCondition,
    GroundProjectionConfig,
    Lanelet2Pose,
    StickyCondition,
    TimeoutCondition,
)

from .configs import OdaibaOutboundConfig

logger = logging.getLogger(__name__)


class OdaibaOutboundScenario(BaseScenario):
    """Pass when the ego reaches the goal box (Aomi)."""

    def __init__(
        self,
        ego_config: EgoConfig,
        spawn_pose: Lanelet2Pose,
        config: OdaibaOutboundConfig | None = None,
        ground_projection: GroundProjectionConfig | None = None,
    ) -> None:
        super().__init__(
            ego_config, spawn_pose=spawn_pose, ground_projection=ground_projection
        )
        self._config = config or OdaibaOutboundConfig()

    def setup(self) -> None:
        """Snap the ego spawn and register the pass/fail conditions."""
        self._setup_ego_spawn()
        cfg = self._config

        # Pass condition: the ego enters a box around the goal centerline point.
        # The box is a Frenet rectangle (s +/- half_length, t +/- half_width),
        # latched via Sticky so a single momentary entry passes the scenario.
        s_lo = cfg.goal_s - cfg.goal_box_half_length
        s_hi = cfg.goal_s + cfg.goal_box_half_length
        w = cfg.goal_box_half_width
        goal_box = [
            Lanelet2Pose(lanelet_id=cfg.goal_lanelet_id, s=s_lo, t=-w),
            Lanelet2Pose(lanelet_id=cfg.goal_lanelet_id, s=s_hi, t=-w),
            Lanelet2Pose(lanelet_id=cfg.goal_lanelet_id, s=s_hi, t=w),
            Lanelet2Pose(lanelet_id=cfg.goal_lanelet_id, s=s_lo, t=w),
        ]
        logger.info(
            "Goal box: lanelet %d, s=[%.2f, %.2f], |t|<=%.2f",
            cfg.goal_lanelet_id,
            s_lo,
            s_hi,
            w,
        )
        self.register_pass_condition(
            StickyCondition(
                EntityInAreaCondition(
                    entity_name=EGO_ROLE_NAME,
                    polygon=goal_box,
                    label="reached_goal",
                )
            )
        )

        # Fail-safe timeout.
        self.register_fail_condition(
            TimeoutCondition(cfg.timeout_seconds, label="scenario_timeout")
        )

    def is_done(self) -> bool:
        """Termination is driven entirely by the pass/fail conditions."""
        return False
