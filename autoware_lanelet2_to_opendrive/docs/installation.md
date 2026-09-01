# Installation

This guide explains how to install the `autoware-lanelet2-to-opendrive` package
either directly on a host or inside the project's pinned Docker image.

## System Requirements

### Operating System

The package targets **Ubuntu 22.04** (the Docker image's base), which is what
CI exercises. Every dependency ships as a prebuilt manylinux wheel, so other
Linux distributions work as long as they can provide CPython 3.10.

### Python Version

- **Python 3.10** (exactly 3.10, not 3.11+) — pinned by `requires-python = ">=3.10,<3.11"`
  in `pyproject.toml`. The pin exists because the bundled CARLA wheel in
  `carla_wheels/` is CPython-3.10 ABI-tagged. `simple-lanelet2` itself ships
  abi3 wheels and does not constrain the interpreter.

### Package Manager

- **uv** 0.9.7 or newer.

## Installing uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

For other installation methods, see the
[uv documentation](https://docs.astral.sh/uv/).

## Installing the Package

### Recommended: Use Docker (matches CI exactly)

A host install works on any Linux distribution that can provide CPython 3.10,
since nothing is compiled from source. Docker is still the way to reproduce CI
byte for byte: the repository ships a multi-stage `Dockerfile` and
`docker-compose.yml` that pin Ubuntu 22.04 and CPython 3.10.

```bash
# Open an interactive shell with the workspace bind-mounted.
docker compose --profile dev run --rm dev

# Run the slim convert image directly (uses the `convert` console script).
docker compose --profile convert run --rm convert input_map_path=/io/map.osm
```

See the [docker docs in the repo root](https://github.com/tier4/autoware_lanelet2_to_opendrive/blob/master/docs/docker.md)
for the full reference of profiles (`dev`, `test`, `lint`, `qc`, `carla`,
`convert`).

### From Source (host install)

To install from source on the host:

```bash
git clone https://github.com/tier4/autoware_lanelet2_to_opendrive.git
cd autoware_lanelet2_to_opendrive

# Sync workspace dependencies from uv.lock (reproducible).
uv sync --dev
```

The repository is a `uv` workspace containing two members
(`autoware_lanelet2_to_opendrive` and `autoware_carla_scenario`); a single
`uv sync` installs both.

To run any of the console scripts:

```bash
uv run convert input_map_path=/path/to/map.osm
uv run preprocess-lanelet config.yaml
uv run analyze output.xodr input.osm
uv run qc-validate output.xodr
uv run carla-import-test output.xodr --map-name my_map
```

### CARLA extra (optional)

The `carla` Python wheel is required only by the `autoware_carla_scenario`
workspace member (used by `carla-import-test` and the `carla` docker-compose
profile). The optional extra is declared on that workspace, not on this
package; the bundled wheels live under `carla_wheels/`:

```bash
# CARLA 0.10.0 (default expected by the carla docker profile)
uv sync --dev --extra carla

# Or pin to CARLA 0.9.16 (mutually exclusive with `carla`)
uv sync --dev --extra carla-0-9-16
```

`uv sync --dev` (without an extra) is sufficient for converting maps,
running unit tests, building docs, and the QC pipeline; the extra is only
needed when actually importing the `carla` Python package.

## Verifying Installation

```bash
uv run python -c "import autoware_lanelet2_to_opendrive; print('OK')"
uv run convert --help
```

## Dependencies

The runtime dependencies declared in
[`autoware_lanelet2_to_opendrive/pyproject.toml`](https://github.com/tier4/autoware_lanelet2_to_opendrive/blob/master/autoware_lanelet2_to_opendrive/pyproject.toml)
are:

- `simple-lanelet2` (>=1.1.2) — the `lanelet2` and `autoware_lanelet2_extension_python`
  import paths, including the Autoware regulatory-element extensions and `MGRSProjector`
- `scipy` (>=1.9.0) — spline fitting and numerical primitives
- `lxml` (>=5.2.2) — OpenDRIVE XML serialization
- `mgrs` (>=1.5.0) — MGRS ↔ lat/lon conversion
- `tqdm` (>=4.67.1) — progress bars
- `pyyaml` (>=6.0.0) — YAML parsing for preprocessing configs
- `hydra-core` (>=1.3.2) — CLI configuration
- `asam-qc-opendrive` (>=1.0.0) — ASAM QC checker (used by `analyze` / `qc-validate`)
- `pyxodr` (>=0.1.3) — OpenDRIVE structural validation

Console scripts registered in `[project.scripts]`:

| Script | Module | Purpose |
|--------|--------|---------|
| `convert` | `autoware_lanelet2_to_opendrive.main:main` | Lanelet2 → OpenDRIVE conversion (Hydra CLI) |
| `preprocess-lanelet` | `autoware_lanelet2_to_opendrive.preprocess_lanelet:main` | Standalone preprocessing of `.osm` files |
| `analyze` | `autoware_lanelet2_to_opendrive.analyze_xodr:main` | ASAM QC + lanelet/road mapping cross-validation |
| `qc-validate` | `autoware_lanelet2_to_opendrive.qc_validate:main` | ASAM QC checker on a standalone `.xodr` |
| `carla-import-test` | `autoware_lanelet2_to_opendrive.carla_import_test:main` | Smoke-test `.xodr` import into a running CARLA server |

## Troubleshooting

### `ModuleNotFoundError` or unexpected behaviour on `import lanelet2`

Usually caused by another distribution owning the same import path — the PyPI
`lanelet2` package, or a ROS `lanelet2` on `PYTHONPATH` — shadowing
`simple-lanelet2`. Reset the venv:

```bash
rm -rf .venv
uv sync --dev
```

## Next Steps

- [Usage Guide](usage.md) — run conversions
- [Development Guide](development.md) — contributing workflow
