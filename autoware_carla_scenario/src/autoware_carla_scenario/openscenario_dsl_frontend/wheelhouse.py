"""Build an offline-installable wheelhouse from a transpiled scenario package.

A *wheelhouse* is a directory of wheels holding the scenario package plus every
transitive dependency -- the framework, third-party libraries, and the native
``lanelet2`` binding. Because every dependency is pre-built, the scenario
installs into a clean virtual environment with no ``uv``, no ``git``, and no
network access::

    pip install --no-index --find-links <wheelhouse> <distribution-name>

Producing the wheelhouse *does* need network access and a build toolchain once
(it compiles the native ``lanelet2`` binding from its git source); the resulting
artifact does not. See ``docs/openscenario_dsl_frontend.md`` for the full flow.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable, Sequence

try:  # Python 3.11+ ships tomllib; the project pins 3.10, so fall back to tomli.
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised only on <3.11
    import tomli as tomllib

from .errors import OscError

#: Signature of the subprocess runner injected for testability. Mirrors the
#: subset of :func:`subprocess.run` the builder relies on.
Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class WheelhouseError(OscError):
    """Raised when the wheelhouse build cannot be completed."""


def _load_pyproject(workspace_root: Path) -> dict:
    return tomllib.loads(
        (workspace_root / "pyproject.toml").read_text(encoding="utf-8")
    )


def _find_workspace_root(start: Path) -> Path:
    """Return the nearest ancestor holding a ``[tool.uv.workspace]`` pyproject.

    The scenario package is generated under the workspace checkout, so building
    its wheels needs the workspace's member layout and git ``[tool.uv.sources]``
    pins. Walking up from *start* locates that root.
    """
    for candidate in (start, *start.parents):
        pyproject = candidate / "pyproject.toml"
        if not pyproject.is_file():
            continue
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        if "workspace" in data.get("tool", {}).get("uv", {}):
            return candidate
    raise WheelhouseError(
        "could not locate the uv workspace root: no pyproject.toml with a "
        f"[tool.uv.workspace] table above {start}. Run osc-transpile from a "
        "checkout of the autoware_lanelet2_to_opendrive workspace."
    )


def _git_source_requirements(workspace_root: Path) -> list[str]:
    """Translate workspace ``[tool.uv.sources]`` git pins into pip requirements.

    The workspace members declare bare dependency names (e.g.
    ``lanelet2-python-api-for-autoware``) that are not published on PyPI; uv
    resolves them via ``[tool.uv.sources]``. ``pip`` knows nothing about those
    sources, so each git-pinned name is re-expressed as a direct-reference
    requirement (``name @ git+<url>@<rev>``) and passed explicitly.
    """
    sources = (
        _load_pyproject(workspace_root).get("tool", {}).get("uv", {}).get("sources", {})
    )
    requirements: list[str] = []
    for name, spec in sources.items():
        if isinstance(spec, dict) and "git" in spec:
            ref = f"@{spec['rev']}" if spec.get("rev") else ""
            requirements.append(f"{name} @ git+{spec['git']}{ref}")
    return requirements


def _workspace_member_dirs(workspace_root: Path) -> list[Path]:
    """Return the on-disk directories of the workspace member projects.

    The generated scenario depends on ``autoware-carla-scenario`` (and, through
    it, the rest of the workspace). Those members are not on PyPI either, so
    their source directories are handed to ``pip wheel`` to be built locally.
    """
    members = (
        _load_pyproject(workspace_root)
        .get("tool", {})
        .get("uv", {})
        .get("workspace", {})
        .get("members", [])
    )
    return [workspace_root / member for member in members]


def _render_wheelhouse_readme(
    distribution_name: str, scenario_names: Sequence[str]
) -> str:
    run_lines = "\n".join(
        f"scenario scenario={name}/default" for name in scenario_names
    )
    return (
        f"# {distribution_name} wheelhouse\n\n"
        "A self-contained wheelhouse: every wheel needed to run this scenario, "
        "including the native `lanelet2` binding. It installs offline, with no "
        "`uv`, `git`, or network access -- only `python3-venv` and "
        "`python3-pip`.\n\n"
        "## Install (offline)\n\n"
        "```bash\n"
        "python3 -m venv .venv\n"
        ". .venv/bin/activate\n"
        f"pip install --no-index --find-links . {distribution_name}\n"
        "```\n\n"
        "Or run the bundled helper: `./install.sh`.\n\n"
        "## Run\n\n"
        "```bash\n"
        f"{run_lines}\n"
        "```\n"
    )


def _render_install_script(distribution_name: str) -> str:
    return (
        "#!/usr/bin/env bash\n"
        "# Offline install of the scenario and all its dependencies from the\n"
        "# wheels bundled in this directory. Needs only python3-venv and\n"
        "# python3-pip -- no uv, git, or network access.\n"
        "set -euo pipefail\n"
        'HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"\n'
        'python3 -m venv "${VENV:-.venv}"\n'
        "# shellcheck disable=SC1091\n"
        '. "${VENV:-.venv}/bin/activate"\n'
        f'pip install --no-index --find-links "$HERE" {distribution_name}\n'
    )


def _write_install_helpers(
    wheelhouse_dir: Path,
    distribution_name: str,
    scenario_names: Sequence[str],
) -> None:
    (wheelhouse_dir / "README.md").write_text(
        _render_wheelhouse_readme(distribution_name, scenario_names),
        encoding="utf-8",
    )
    script = wheelhouse_dir / "install.sh"
    script.write_text(_render_install_script(distribution_name), encoding="utf-8")
    script.chmod(0o755)


def build_wheelhouse(
    package_src: str | Path,
    wheelhouse_dir: str | Path,
    distribution_name: str,
    scenario_names: Sequence[str],
    *,
    workspace_root: str | Path | None = None,
    python_executable: str = sys.executable,
    runner: Runner = subprocess.run,
) -> Path:
    """Build a complete offline wheelhouse for a transpiled scenario package.

    A single ``pip wheel`` invocation builds the scenario, every workspace
    member, the git-pinned dependencies, and the entire transitive PyPI closure
    into *wheelhouse_dir*, then offline-install helpers are written alongside.

    Args:
        package_src: Directory holding the generated scenario package source.
        wheelhouse_dir: Directory to populate with wheels (created if absent).
        distribution_name: Installable name of the scenario distribution, used
            in the generated install instructions.
        scenario_names: Scenario config names, used in the run instructions.
        workspace_root: Workspace root; auto-detected from *package_src* if
            omitted.
        python_executable: Interpreter whose ``pip`` builds the wheels.
        runner: Subprocess runner (injected for testing).

    Returns:
        The populated wheelhouse directory.

    Raises:
        WheelhouseError: If the workspace cannot be located or ``pip wheel``
            fails (e.g. the host lacks the toolchain to compile ``lanelet2``).
    """
    package_src = Path(package_src)
    wheelhouse_dir = Path(wheelhouse_dir)
    root = (
        Path(workspace_root)
        if workspace_root is not None
        else _find_workspace_root(package_src.resolve())
    )

    wheelhouse_dir.mkdir(parents=True, exist_ok=True)

    build_targets = [
        str(package_src),
        *(str(d) for d in _workspace_member_dirs(root)),
        *_git_source_requirements(root),
    ]
    command = [
        python_executable,
        "-m",
        "pip",
        "wheel",
        "--wheel-dir",
        str(wheelhouse_dir),
        *build_targets,
    ]
    result = runner(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise WheelhouseError(
            "failed to build the wheelhouse "
            f"(pip wheel exited {result.returncode}).\n"
            "Building the wheelhouse compiles the native lanelet2 binding, "
            "which needs a full build toolchain and network access. Run inside "
            "the project's Docker container (see docs/docker.md) if the host "
            "cannot build it.\n\n"
            f"command: {' '.join(command)}\n\n"
            f"{result.stderr or result.stdout}"
        )

    _write_install_helpers(wheelhouse_dir, distribution_name, scenario_names)
    return wheelhouse_dir
