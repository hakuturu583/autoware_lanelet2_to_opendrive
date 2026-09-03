"""Config dataclass for the ``odaiba_outbound`` scenario.

The scenario's parameters live with the scenario, in this package -- not inside
``autoware_carla_scenario``.  Shared parameters (ego, map, server, ...) can be
imported from the framework's public API instead of being redefined here.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OdaibaOutboundConfig:
    """Parameters for the ``odaiba_outbound`` scenario.

    The goal is expressed in Lanelet2 (Frenet) coordinates so the pass check
    works on a lanelet2-only map -- no OpenDRIVE required.  A rectangular box
    around the goal centerline point (``goal_s`` +/- ``goal_box_half_length``,
    ``t`` in +/- ``goal_box_half_width``) defines the pass area.

    Every field is overridable from YAML (and the CLI) via Hydra, e.g.::

        uv run scenario scenario=odaiba_outbound/default \\
            scenario.timeout_seconds=600
    """

    #: Must match the name passed to ``register_scenario`` and the
    #: ``scenario.name`` key in the YAML config.
    name: str = "odaiba_outbound"

    #: Lanelet ID of the goal (Aomi).  Its centerline defines the pass box.
    goal_lanelet_id: int = 175965

    #: Arc length (m) along the goal lanelet's centerline at the goal point.
    goal_s: float = 50.29

    #: Half-length (m) of the pass box along the centerline (s direction).
    goal_box_half_length: float = 5.0

    #: Half-width (m) of the pass box across the centerline (t direction).
    goal_box_half_width: float = 3.0

    #: Fail-safe timeout in seconds.  The outbound route is long, so give the
    #: closed loop generous headroom (Autoware routes, engages, then drives).
    timeout_seconds: float = 900.0
