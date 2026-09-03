"""Unit tests for the OpenDRIVE-usage decorator + source scan.

CARLA-free: exercises the ``requires_opendrive`` decorator and the AST scan with
locally-declared symbols, so it needs no live framework import.

The decorator marks only OpenDRIVE *leaf* functions; higher-level condition
classes are intentionally left undecorated (their OpenDRIVE requirement is
enforced precisely at run time by the ``MapManager`` accessors, i.e. only when an
OpenDRIVE code path is actually reached).  These tests reflect that: a leaf
function is flagged, while a condition-class-style name is not.
"""

from __future__ import annotations

import pytest

from autoware_carla_scenario.opendrive_lint import (
    check_scenario_source,
    find_opendrive_symbols,
    opendrive_symbols,
    requires_opendrive,
)


@requires_opendrive
def _my_od_leaf() -> None:
    """Stand-in for a real OpenDRIVE leaf (e.g. ``to_opendrive``)."""


# NOT decorated: a condition class reaches OpenDRIVE only through leaves, so the
# static scan must not flag it -- it may run fine on a Lanelet2-only map when its
# OpenDRIVE path is never taken.
class _MyOdCapableCondition:
    pass


def test_decorator_registers_and_marks() -> None:
    assert "_my_od_leaf" in opendrive_symbols()
    assert getattr(_my_od_leaf, "requires_opendrive", False) is True


def test_condition_class_is_not_registered() -> None:
    # Only leaf functions are declared; condition classes are guarded at run time.
    assert "_MyOdCapableCondition" not in opendrive_symbols()


def test_find_flags_referenced_leaf() -> None:
    source = "class S:\n    def setup(self):\n        _my_od_leaf()\n"
    assert find_opendrive_symbols(source) == {"_my_od_leaf"}


def test_find_resolves_import_aliases() -> None:
    source = "from somewhere import _my_od_leaf as foo\n\nfoo()\n"
    assert find_opendrive_symbols(source) == {"_my_od_leaf"}


def test_find_ignores_condition_class_reference() -> None:
    # A scenario that only names an OpenDRIVE-capable *condition* is not flagged;
    # whether OpenDRIVE is truly needed is decided at the reached code path.
    source = "class S:\n    def setup(self):\n        _MyOdCapableCondition()\n"
    assert find_opendrive_symbols(source) == set()


def test_find_ignores_unregistered_names() -> None:
    # EntityInAreaCondition is deliberately NOT registered (it is OpenDRIVE-free).
    source = "class S:\n    def setup(self):\n        EntityInAreaCondition()\n"
    assert find_opendrive_symbols(source) == set()


def test_check_raises_for_opendrive_usage() -> None:
    with pytest.raises(ValueError, match="OpenDRIVE"):
        check_scenario_source("_my_od_leaf()", "S")


def test_check_passes_without_opendrive_usage() -> None:
    check_scenario_source("x = 1\n", "S")  # must not raise
