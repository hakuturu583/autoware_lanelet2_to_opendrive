"""Pytest configuration and fixtures."""

import os
from pathlib import Path

import pytest

# Import autoware extensions before any tests to ensure proper registration.
# Both projection AND regulatory_elements must be imported so that the
# lanelet2 C++ factory recognises custom types (AutowareTrafficLight,
# RoadMarking, DetectionArea, etc.) when loading maps.
from autoware_lanelet2_extension_python.projection import MGRSProjector  # noqa: F401
import autoware_lanelet2_extension_python.regulatory_elements as _ll2_ext_reg  # noqa: F401
import lanelet2  # noqa: F401


# git exports the variables that locate a repository (`git rev-parse
# --local-env-vars`) to its hooks, and the pre-commit hooks run this suite: left
# in place they point every `git` the tests run in a scratch directory at the
# repository being committed to -- writing into its index and config.
for _var in (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_DIR",
    "GIT_GRAFT_FILE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_INTERNAL_SUPER_PREFIX",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_OBJECT_DIRECTORY",
    "GIT_PREFIX",
    "GIT_REPLACE_REF_BASE",
    "GIT_SHALLOW_FILE",
    "GIT_WORK_TREE",
):
    os.environ.pop(_var, None)


@pytest.fixture(scope="session")
def lanelet_map():
    """Load test map once and cache for entire test session.

    This fixture loads the large nishishinjuku.osm file (11MB, 307k lines) once
    per test session and reuses it across all tests. This significantly reduces
    test execution time by avoiding repeated file I/O and parsing.

    Returns:
        lanelet2.core.LaneletMap: The loaded lanelet2 map.
    """
    test_data_path = Path(__file__).parent / "data" / "nishishinjuku.osm"
    projector = MGRSProjector(
        lanelet2.io.Origin(35.23, 139.16)
    )  # MGRS origin for Tokyo area (54SUE)
    return lanelet2.io.load(str(test_data_path), projector)
