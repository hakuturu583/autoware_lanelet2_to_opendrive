"""Unit tests for the offline wheelhouse builder.

Building a real wheelhouse compiles the native ``lanelet2`` binding, which
needs a full toolchain and network access and therefore cannot run in every
environment (see ``docs/docker.md``). These tests instead inject a fake
subprocess runner, so they verify the *orchestration* -- the ``pip wheel``
command composition, the generated offline-install helpers, and error handling
-- without invoking pip. The pure workspace-introspection helpers are checked
against the real workspace ``pyproject.toml``.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
from pathlib import Path

import pytest

from autoware_carla_scenario.openscenario_dsl_frontend.wheelhouse import (
    WheelhouseError,
    _find_workspace_root,
    _git_source_requirements,
    _render_install_script,
    _render_wheelhouse_readme,
    _workspace_member_dirs,
    build_wheelhouse,
)

_HAS_OSC2 = importlib.util.find_spec("osc2parser") is not None
_requires_osc2 = pytest.mark.skipif(
    not _HAS_OSC2, reason="py-osc2 is not installed (isolated-env dependency)"
)

_WORKSPACE_ROOT = _find_workspace_root(Path(__file__).resolve())
_EXAMPLE_OSC = (
    _WORKSPACE_ROOT
    / "autoware_carla_scenario"
    / "examples"
    / "openscenario"
    / "intersection_passing.osc"
)


class _FakeRunner:
    """Records the command it is called with and returns a canned result."""

    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.returncode = returncode
        self.stderr = stderr
        self.calls: list[list[str]] = []

    def __call__(self, command, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(command))
        return subprocess.CompletedProcess(
            command, self.returncode, stdout="", stderr=self.stderr
        )


# ---------------------------------------------------------------------------
# Workspace introspection (pure; reads the real workspace pyproject)
# ---------------------------------------------------------------------------


def test_find_workspace_root_locates_uv_workspace() -> None:
    assert (_WORKSPACE_ROOT / "pyproject.toml").is_file()
    # The scenario package is generated deep under the workspace; discovery must
    # still find the root from an arbitrary descendant.
    nested = _WORKSPACE_ROOT / "autoware_carla_scenario" / "src"
    assert _find_workspace_root(nested) == _WORKSPACE_ROOT


def test_find_workspace_root_raises_outside_workspace(tmp_path: Path) -> None:
    with pytest.raises(WheelhouseError, match="workspace root"):
        _find_workspace_root(tmp_path)


def test_git_source_requirements_reexpress_git_pins() -> None:
    reqs = _git_source_requirements(_WORKSPACE_ROOT)
    names = {req.split(" @ ", 1)[0] for req in reqs}
    assert "lanelet2-python-api-for-autoware" in names
    assert "asam-qc-opendrive" in names
    for req in reqs:
        # Each is a pip direct-reference to a pinned git revision.
        assert " @ git+" in req
        assert "@" in req.split("git+", 1)[1]


def test_workspace_member_dirs_are_the_project_dirs() -> None:
    members = _workspace_member_dirs(_WORKSPACE_ROOT)
    assert _WORKSPACE_ROOT / "autoware_carla_scenario" in members
    assert _WORKSPACE_ROOT / "autoware_lanelet2_to_opendrive" in members


# ---------------------------------------------------------------------------
# Offline-install helper rendering
# ---------------------------------------------------------------------------


def test_readme_documents_offline_install() -> None:
    readme = _render_wheelhouse_readme("my-scenario-package", ["variant_a"])
    assert "pip install --no-index --find-links . my-scenario-package" in readme
    assert "scenario scenario=variant_a/default" in readme


def test_install_script_is_offline_and_pins_distribution() -> None:
    script = _render_install_script("my-scenario-package")
    assert script.startswith("#!/usr/bin/env bash")
    assert "--no-index" in script
    assert "my-scenario-package" in script


# ---------------------------------------------------------------------------
# build_wheelhouse orchestration (fake runner)
# ---------------------------------------------------------------------------


def test_build_wheelhouse_composes_pip_wheel_command(tmp_path: Path) -> None:
    package_src = tmp_path / "pkg"
    package_src.mkdir()
    wheelhouse = tmp_path / "wh"
    runner = _FakeRunner()

    result = build_wheelhouse(
        package_src,
        wheelhouse,
        "my-scenario-package",
        ["variant_a"],
        workspace_root=_WORKSPACE_ROOT,
        runner=runner,
    )

    assert result == wheelhouse
    (command,) = runner.calls
    assert command[1:4] == ["-m", "pip", "wheel"]
    assert "--wheel-dir" in command
    assert str(wheelhouse) in command
    # Builds the scenario source, every workspace member, and the git pins.
    assert str(package_src) in command
    for member in _workspace_member_dirs(_WORKSPACE_ROOT):
        assert str(member) in command
    for req in _git_source_requirements(_WORKSPACE_ROOT):
        assert req in command


def test_build_wheelhouse_writes_install_helpers(tmp_path: Path) -> None:
    package_src = tmp_path / "pkg"
    package_src.mkdir()
    wheelhouse = tmp_path / "wh"

    build_wheelhouse(
        package_src,
        wheelhouse,
        "my-scenario-package",
        ["variant_a"],
        workspace_root=_WORKSPACE_ROOT,
        runner=_FakeRunner(),
    )

    readme = wheelhouse / "README.md"
    script = wheelhouse / "install.sh"
    assert readme.is_file()
    assert script.is_file()
    assert "my-scenario-package" in readme.read_text(encoding="utf-8")
    # The helper must be executable so `./install.sh` works out of the box.
    assert os.stat(script).st_mode & stat.S_IXUSR


def test_build_wheelhouse_raises_on_pip_failure(tmp_path: Path) -> None:
    package_src = tmp_path / "pkg"
    package_src.mkdir()
    wheelhouse = tmp_path / "wh"
    runner = _FakeRunner(returncode=1, stderr="boost not found")

    with pytest.raises(WheelhouseError) as excinfo:
        build_wheelhouse(
            package_src,
            wheelhouse,
            "my-scenario-package",
            ["variant_a"],
            workspace_root=_WORKSPACE_ROOT,
            runner=runner,
        )

    message = str(excinfo.value)
    assert "pip wheel exited 1" in message
    assert "boost not found" in message
    # A failed build must not leave install helpers implying success.
    assert not (wheelhouse / "install.sh").exists()


# ---------------------------------------------------------------------------
# transpiler helpers (pure; no py-osc2)
# ---------------------------------------------------------------------------


def _synthetic_files() -> dict[str, str]:
    return {
        "pyproject.toml": '[project]\nname = "intersection-passing-package"\n',
        "src/intersection_passing_package/__init__.py": "x = 1\n",
        "src/intersection_passing_package/conf/scenario/foo/default.yaml": "a: 1\n",
        "src/intersection_passing_package/conf/scenario/bar/default.yaml": "a: 2\n",
    }


def test_distribution_name_reads_generated_pyproject() -> None:
    from autoware_carla_scenario.openscenario_dsl_frontend.transpiler import (
        _distribution_name,
        _package_dir_name,
        _scenario_config_names,
    )

    files = _synthetic_files()
    assert _distribution_name(files["pyproject.toml"]) == "intersection-passing-package"
    assert _package_dir_name(files) == "intersection_passing_package"
    assert _scenario_config_names(files) == ["foo", "bar"]


# ---------------------------------------------------------------------------
# transpile_to_wheelhouse end-to-end (needs py-osc2; fake runner)
# ---------------------------------------------------------------------------


@_requires_osc2
def test_transpile_to_wheelhouse_builds_named_directory(tmp_path: Path) -> None:
    from autoware_carla_scenario.openscenario_dsl_frontend.transpiler import (
        transpile_to_wheelhouse,
    )

    runner = _FakeRunner()
    wheelhouse = transpile_to_wheelhouse(
        _EXAMPLE_OSC,
        output_dir=tmp_path,
        runner=runner,
    )

    assert wheelhouse.parent == tmp_path
    assert wheelhouse.name.endswith("_wheelhouse")
    assert (wheelhouse / "install.sh").is_file()
    # The generated (temporary) source tree is the first pip wheel target.
    (command,) = runner.calls
    assert command[1:4] == ["-m", "pip", "wheel"]


@_requires_osc2
def test_transpile_to_wheelhouse_refuses_existing_without_force(
    tmp_path: Path,
) -> None:
    from autoware_carla_scenario.openscenario_dsl_frontend.transpiler import (
        transpile_to_wheelhouse,
    )

    runner = _FakeRunner()
    first = transpile_to_wheelhouse(_EXAMPLE_OSC, output_dir=tmp_path, runner=runner)
    assert first.is_dir()

    with pytest.raises(FileExistsError):
        transpile_to_wheelhouse(_EXAMPLE_OSC, output_dir=tmp_path, runner=runner)

    # force overwrites cleanly.
    again = transpile_to_wheelhouse(
        _EXAMPLE_OSC, output_dir=tmp_path, force=True, runner=runner
    )
    assert again == first
