"""Every subpackage must import on its own.

A cycle between two packages does not necessarily raise.  Whether it does
depends on which one an entry point reaches first, so a cycle can sit in the
tree indefinitely while ``import autoware_carla_scenario`` -- the order every
test happens to take -- keeps working, and surface only when something imports a
subpackage directly.  That is what happened to ``coordinate`` and ``utils``:
``coordinate/__init__`` imports ``coordinate.stop_line``, which imports
``utils.stop_line``, which imported ``coordinate.map_manager`` straight back.

Each import runs in its own interpreter, because the check is about import
*order* and a module already in ``sys.modules`` cannot demonstrate anything.
"""

from __future__ import annotations

import pkgutil
import subprocess
import sys

import pytest

import autoware_carla_scenario


def _subpackages() -> list[str]:
    """Return every importable subpackage, discovered rather than listed."""
    return sorted(
        f"{autoware_carla_scenario.__name__}.{info.name}"
        for info in pkgutil.iter_modules(autoware_carla_scenario.__path__)
        if info.ispkg
    )


@pytest.mark.parametrize("module", _subpackages())
def test_a_subpackage_imports_on_its_own(module: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"{module} does not import on its own:\n{result.stderr}"


def test_the_sweeper_map_loader_imports_on_its_own() -> None:
    """The path that first exposed the cycle, named so a regression is legible.

    ``sweeper/__init__`` -> ``bindings`` -> ``utils/__init__`` ->
    ``utils.stop_line`` -> ``coordinate`` -> ``coordinate.stop_line`` -> back
    into a half-built ``utils.stop_line``.
    """
    result = subprocess.run(
        [sys.executable, "-c", "import autoware_carla_scenario.sweeper.map_loader"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
