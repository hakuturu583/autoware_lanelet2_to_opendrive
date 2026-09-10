"""High-level entry points that tie the frontend pipeline together.

The pipeline is::

    .osc source
        -> parser.parse_*             (py-osc2 / ANTLR parse tree)
        -> extractor.extract          (syntax IR: OscProgram)
        -> translator.translate       (semantic plan: ScenarioPlan)
        -> package_codegen.generate   (installable scenario package)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:  # Python 3.11+ ships tomllib; the project pins 3.10, so fall back to tomli.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on <3.11
    import tomli as tomllib

from .ast_model import OscProgram
from .extractor import extract_program
from .package_codegen import generate_package_files
from .parser import parse_osc_file, parse_osc_string
from .plan import ScenarioPlan
from .translator import translate_program
from .wheelhouse import Runner, _find_workspace_root, build_wheelhouse


def parse_program_from_file(path: str | Path) -> OscProgram:
    """Parse and extract a ``.osc`` file into an :class:`OscProgram`."""
    return extract_program(parse_osc_file(path))


def parse_program_from_string(
    text: str, *, source_name: str = "<string>"
) -> OscProgram:
    """Parse and extract DSL source text into an :class:`OscProgram`."""
    return extract_program(parse_osc_string(text, source_name=source_name))


def plans_from_file(path: str | Path) -> list[ScenarioPlan]:
    """Parse, extract and translate a ``.osc`` file into scenario variants.

    Returns one :class:`ScenarioPlan` per ``one_of`` branch combination (just
    one for a scenario without ``one_of``).
    """
    return translate_program(parse_program_from_file(path))


def plans_from_string(
    text: str, *, source_name: str = "<string>"
) -> list[ScenarioPlan]:
    """Parse, extract and translate DSL source text into scenario variants."""
    return translate_program(parse_program_from_string(text, source_name=source_name))


def transpile_to_package(
    source: str | Path,
    output_dir: str | Path = ".",
    *,
    package_name: str | None = None,
    description: str | None = None,
    force: bool = False,
) -> Path:
    """Transpile *source* into an installable scenario package under *output_dir*.

    Args:
        source: Path to the ``.osc`` source.
        output_dir: Parent directory to create the package directory in.
        package_name: Desired package name; defaults to ``<scenario>_package``.
        description: Optional package description.
        force: Overwrite existing files if the target directory exists.

    Returns:
        The created package root directory.

    Raises:
        FileExistsError: If the target directory exists and *force* is ``False``.
    """
    plans = plans_from_file(source)
    files = generate_package_files(
        plans,
        source_name=str(source),
        package_name=package_name,
        description=description,
    )
    pkg = _package_dir_name(files)
    root = Path(output_dir) / pkg
    if root.exists() and not force:
        raise FileExistsError(
            f"target directory already exists: {root} (use force=True to overwrite)"
        )
    _materialize(files, root)
    return root


def _package_dir_name(files: dict[str, str]) -> str:
    """Return the ``src/<pkg>`` package directory name from a file mapping."""
    return next(key.split("/")[1] for key in files if key.startswith("src/"))


def _materialize(files: dict[str, str], root: Path) -> None:
    """Write a ``{relative_path: content}`` package mapping under *root*."""
    for rel, content in files.items():
        out_path = root / rel
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(content, encoding="utf-8")


def _distribution_name(pyproject_text: str) -> str:
    """Extract ``[project].name`` from a generated ``pyproject.toml``."""
    return tomllib.loads(pyproject_text)["project"]["name"]


def _scenario_config_names(files: dict[str, str]) -> list[str]:
    """Return the scenario config names from generated ``conf/scenario`` paths."""
    marker = "/conf/scenario/"
    names: list[str] = []
    for key in files:
        if marker in key and key.endswith("default.yaml"):
            names.append(key.split(marker, 1)[1].split("/", 1)[0])
    return names


def transpile_to_wheelhouse(
    source: str | Path,
    output_dir: str | Path = ".",
    *,
    package_name: str | None = None,
    description: str | None = None,
    force: bool = False,
    workspace_root: str | Path | None = None,
    python_executable: str = sys.executable,
    runner: Runner = subprocess.run,
) -> Path:
    """Transpile *source* into an offline-installable wheelhouse under *output_dir*.

    The scenario package is generated into a temporary source tree, then it and
    its entire dependency closure -- workspace members, git-pinned sources, and
    the transitive PyPI graph -- are built into a wheelhouse directory named
    ``<package>_wheelhouse``. The wheelhouse installs into a clean virtualenv
    with no ``uv``, ``git``, or network access; see :mod:`.wheelhouse`.

    Args:
        source: Path to the ``.osc`` source.
        output_dir: Parent directory to create the wheelhouse directory in.
        package_name: Desired package name; defaults to ``<scenario>_package``.
        description: Optional package description.
        force: Overwrite an existing wheelhouse directory if present.
        workspace_root: Workspace root; auto-detected if omitted.
        python_executable: Interpreter whose ``pip`` builds the wheels.
        runner: Subprocess runner (injected for testing).

    Returns:
        The created wheelhouse directory.

    Raises:
        FileExistsError: If the wheelhouse directory exists and *force* is
            ``False``.
        WheelhouseError: If the wheelhouse build fails.
    """
    plans = plans_from_file(source)
    files = generate_package_files(
        plans,
        source_name=str(source),
        package_name=package_name,
        description=description,
    )
    pkg = _package_dir_name(files)
    distribution_name = _distribution_name(files["pyproject.toml"])
    scenario_names = _scenario_config_names(files)

    # The package source is materialized into a temp dir outside the workspace,
    # so the workspace root (needed for member/git-source resolution) is located
    # from this module's own location within the workspace instead.
    if workspace_root is None:
        workspace_root = _find_workspace_root(Path(__file__).resolve())

    wheelhouse_dir = Path(output_dir) / f"{pkg}_wheelhouse"
    if wheelhouse_dir.exists():
        if not force:
            raise FileExistsError(
                f"target directory already exists: {wheelhouse_dir} "
                "(use force=True to overwrite)"
            )
        # Clear stale wheels so a rebuild never mixes old and new artifacts.
        shutil.rmtree(wheelhouse_dir)

    with tempfile.TemporaryDirectory() as tmp:
        package_src = Path(tmp) / pkg
        _materialize(files, package_src)
        return build_wheelhouse(
            package_src,
            wheelhouse_dir,
            distribution_name,
            scenario_names,
            workspace_root=workspace_root,
            python_executable=python_executable,
            runner=runner,
        )
