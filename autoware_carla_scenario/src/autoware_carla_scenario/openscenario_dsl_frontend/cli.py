"""Command-line interface for the OpenSCENARIO DSL frontend.

Installed as the ``osc-transpile`` console script; it transpiles a ``.osc``
source into an offline-installable ``autoware_carla_scenario`` scenario
wheelhouse::

    osc-transpile scenario.osc                 # create ./<scenario>_package_wheelhouse
    osc-transpile scenario.osc -o out/         # create it under out/
    osc-transpile scenario.osc --name my_pkg   # choose the package name
    osc-transpile scenario.osc --check         # syntax-check only, no output

The wheelhouse bundles the scenario and its entire dependency closure as
wheels, so it installs into a clean virtual environment with no ``uv``,
``git``, or network access::

    pip install --no-index --find-links <wheelhouse> <distribution-name>
"""

from __future__ import annotations

import argparse
import sys

from .errors import OscError
from .parser import parse_osc_file
from .transpiler import transpile_to_wheelhouse


def _build_argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osc-transpile",
        description=(
            "Transpile an OpenSCENARIO DSL (.osc) file into an offline-"
            "installable autoware_carla_scenario scenario wheelhouse."
        ),
    )
    parser.add_argument("source", help="Path to the .osc source file")
    parser.add_argument(
        "-o",
        "--output-dir",
        default=".",
        help="Directory to create the wheelhouse in (default: current directory)",
    )
    parser.add_argument(
        "--name",
        help="Package name (default: <scenario>_package)",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite an existing wheelhouse directory if present",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only parse and syntax-check the source; produce no output",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``osc-transpile`` console script."""
    args = _build_argparser().parse_args(argv)
    try:
        if args.check:
            parse_osc_file(args.source)
            print(f"OK: {args.source} parsed without errors", file=sys.stderr)
            return 0

        wheelhouse = transpile_to_wheelhouse(
            args.source,
            output_dir=args.output_dir,
            package_name=args.name,
            force=args.force,
        )
        print(f"Created scenario wheelhouse at {wheelhouse}", file=sys.stderr)
        print("\nNext steps (offline, no uv/git/network):", file=sys.stderr)
        print(f"  cd {wheelhouse} && ./install.sh", file=sys.stderr)
        print("  # or, into an existing environment:", file=sys.stderr)
        print(
            f"  pip install --no-index --find-links {wheelhouse} <distribution-name>",
            file=sys.stderr,
        )
        print(
            "  scenario scenario=<name>/default map=nishishinjuku",
            file=sys.stderr,
        )
        return 0
    except OscError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
