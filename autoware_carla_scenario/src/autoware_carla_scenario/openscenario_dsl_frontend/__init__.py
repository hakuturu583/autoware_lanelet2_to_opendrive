"""OpenSCENARIO DSL frontend for ``autoware_carla_scenario``.

Parses ASAM OpenSCENARIO DSL (OSC2, ``.osc``) sources with `py-osc2
<https://github.com/PMSFIT/py-osc2>`_ and transpiles them into an
offline-installable :mod:`autoware_carla_scenario` **scenario wheelhouse** -- a
directory of wheels (the scenario plus its whole dependency closure) that
installs with plain ``pip`` and no ``uv``, ``git``, or network access.

Pipeline
--------
``.osc`` source →
:func:`~.parser.parse_osc_file` (ANTLR parse tree) →
:func:`~.extractor.extract_program` (syntax IR, :class:`~.ast_model.OscProgram`) →
:func:`~.translator.translate_program` (semantic plans, :class:`~.plan.ScenarioPlan`) →
:func:`~.package_codegen.generate_package_files` (scenario package source) →
:func:`~.wheelhouse.build_wheelhouse` (offline wheelhouse).

Typical use::

    from autoware_carla_scenario.openscenario_dsl_frontend import (
        transpile_to_wheelhouse,
    )

    wheelhouse = transpile_to_wheelhouse("my_scenario.osc", output_dir="out")
    # pip install --no-index --find-links {wheelhouse} <distribution-name>

:func:`~.transpiler.transpile_to_package` writes just the editable package
source tree instead, for development against a live workspace.

The parse/extract/translate/codegen layers are pure Python and do not import
CARLA, so they can be used (and tested) without a CARLA installation.  Only the
*generated* package's scenario module imports CARLA-backed modules at run time.
"""

from __future__ import annotations

from .errors import (
    OscDependencyError,
    OscError,
    OscParseError,
    OscTranslationError,
)
from .plan import ActorPlan, Gate, ScenarioPlan, Spec, SpecKind, SpecRole
from .registry import register_behavior, register_modifier
from .transpiler import (
    parse_program_from_file,
    parse_program_from_string,
    plans_from_file,
    plans_from_string,
    transpile_to_package,
    transpile_to_wheelhouse,
)
from .wheelhouse import WheelhouseError

__all__ = [
    "ActorPlan",
    "Gate",
    "OscDependencyError",
    "OscError",
    "OscParseError",
    "OscTranslationError",
    "ScenarioPlan",
    "Spec",
    "SpecKind",
    "SpecRole",
    "WheelhouseError",
    "parse_program_from_file",
    "parse_program_from_string",
    "plans_from_file",
    "plans_from_string",
    "register_behavior",
    "register_modifier",
    "transpile_to_package",
    "transpile_to_wheelhouse",
]
