"""Declare and statically check OpenDRIVE usage in a scenario.

A map loaded Lanelet2-only (no ``.xodr`` and no CARLA-sourced OpenDRIVE; see
:class:`~autoware_carla_scenario.coordinate.map_manager.MapManager`) cannot serve
OpenDRIVE-based conversions.  The precise, authoritative guard against that is at
run time: the :class:`MapManager` accessors (notably :attr:`MapManager.road_network`)
raise exactly when -- and only when -- an OpenDRIVE code path is actually reached.
A scenario that references an OpenDRIVE-capable condition but never exercises its
OpenDRIVE path on a Lanelet2-only map is therefore *not* rejected.

The decorator here is deliberately narrow: it marks only the OpenDRIVE **leaf**
functions -- the lowest-level operations that unavoidably need OpenDRIVE
(``to_opendrive``, ``project_onto_road``, the stop-line pose lookups).  Higher-level
condition classes (``EntityLanePositionCondition`` etc.) are intentionally *not*
decorated: they touch OpenDRIVE only *through* these leaves, so their requirement is
already enforced -- precisely, at the reached code path -- by the runtime accessors.

The source scan (:func:`check_scenario_source`) is thus a best-effort *early* check
for the one unambiguous case a static read can be sure of: a scenario whose source
*directly* names an OpenDRIVE-only leaf.  That is the only situation where failing
before spinning CARLA up is provably correct rather than a guess about which runtime
path a condition will take.
"""

from __future__ import annotations

import ast
from typing import TypeVar

_T = TypeVar("_T")

#: Names declared with :func:`requires_opendrive`, populated at import time as the
#: decorated modules load.  The source scan matches against this registry, so
#: adding a decorator is all it takes to include a new symbol -- no list to keep
#: in sync.
_OPENDRIVE_SYMBOLS: set[str] = set()


def requires_opendrive(obj: _T) -> _T:
    """Mark an OpenDRIVE **leaf** function as unavoidably needing OpenDRIVE.

    Sets ``requires_opendrive = True`` on *obj* (self-documenting) and registers its
    name for the source scan (:func:`find_opendrive_symbols`).

    Apply this only to the lowest-level functions that cannot run without OpenDRIVE,
    not to higher-level condition classes that merely call into them -- those are
    guarded precisely at run time by the :class:`MapManager` accessors, so decorating
    them would reject scenarios that never actually reach an OpenDRIVE code path.
    """
    obj.requires_opendrive = True  # type: ignore[attr-defined]
    _OPENDRIVE_SYMBOLS.add(obj.__name__)  # type: ignore[attr-defined]
    return obj


def opendrive_symbols() -> frozenset[str]:
    """Return the currently registered OpenDRIVE-requiring symbol names."""
    return frozenset(_OPENDRIVE_SYMBOLS)


def find_opendrive_symbols(source: str) -> set[str]:
    """Return the registered OpenDRIVE-requiring symbols referenced in *source*.

    Resolves ``import x as y`` / ``from m import x as y`` aliases so a renamed
    import is still matched by its original name.

    Args:
        source: Python source text of the scenario module.

    Returns:
        The subset of :func:`opendrive_symbols` referenced by name in *source*.
    """
    tree = ast.parse(source)

    alias_to_original: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.asname:
                    alias_to_original[alias.asname] = alias.name.split(".")[-1]

    symbols = _OPENDRIVE_SYMBOLS
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            name = node.id
        elif isinstance(node, ast.Attribute):
            name = node.attr
        else:
            continue
        original = alias_to_original.get(name, name)
        if original in symbols:
            found.add(original)
    return found


def check_scenario_source(source: str, scenario_name: str) -> None:
    """Raise if *source* uses OpenDRIVE symbols (for a Lanelet2-only map).

    Args:
        source: Python source text of the scenario module.
        scenario_name: Name used in the error message.

    Raises:
        ValueError: If the scenario references any OpenDRIVE-requiring symbol.
    """
    used = find_opendrive_symbols(source)
    if used:
        raise ValueError(
            f"Scenario {scenario_name!r} uses OpenDRIVE-based symbols "
            f"{sorted(used)} but the map is loaded Lanelet2-only (no OpenDRIVE). "
            "Rewrite these in Lanelet2/map coordinates (e.g. EntityInAreaCondition "
            "or WaypointCondition), or provide an OpenDRIVE (an .xodr file or a "
            "CARLA level whose map carries a geoReference)."
        )
