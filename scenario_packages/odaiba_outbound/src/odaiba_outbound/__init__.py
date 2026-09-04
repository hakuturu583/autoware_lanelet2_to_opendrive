"""Odaiba outbound closed-loop scenario (autoware_ego)

Installing this package and running the framework CLI makes the
``odaiba_outbound`` scenario (and its ``map=odaiba`` group) available without
editing ``autoware_carla_scenario``::

    uv run scenario scenario=odaiba_outbound/default
"""

from __future__ import annotations

import os
from pathlib import Path

from autoware_carla_scenario import register_conf_dir, register_scenario

from .configs import OdaibaOutboundConfig

__all__ = ["OdaibaOutboundConfig", "register"]

#: Directory holding this package's Hydra config groups (scenario/, map/, ...).
CONF_DIR = Path(__file__).resolve().parent / "conf"

#: Lanelet2 map bundled inside this package; the ``map=odaiba`` config points
#: at it via ``ODAIBA_LANELET2_PATH`` (see :func:`register`).
BUNDLED_LANELET2_MAP = Path(__file__).resolve().parent / "maps" / "odaiba.osm"


def register() -> None:
    """Register this package's scenarios and config directory.

    Called automatically by the ``scenario`` CLI via the
    ``autoware_carla_scenario.scenarios`` entry point.

    The scenario class is imported *inside* this function on purpose: importing
    it pulls in ``BaseScenario`` (and therefore CARLA), so deferring it keeps
    merely importing this package -- e.g. while enumerating entry points --
    free of the heavy CARLA import.
    """
    from .odaiba_outbound import OdaibaOutboundScenario

    # Point the ``map=odaiba`` group at the bundled map unless the operator has
    # overridden it (env var wins, so a different map can be supplied at deploy
    # time without touching the package).
    os.environ.setdefault("ODAIBA_LANELET2_PATH", str(BUNDLED_LANELET2_MAP))

    register_scenario("odaiba_outbound", OdaibaOutboundScenario, OdaibaOutboundConfig)
    register_conf_dir(CONF_DIR)
