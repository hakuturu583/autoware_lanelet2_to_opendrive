# odaiba-outbound

A standalone **scenario package** for the
[`autoware-carla-scenario`](https://github.com/tier4/autoware_lanelet2_to_opendrive)
framework, generated with `scenario-new`. Its scenario and config dataclass
live here, outside the framework.

## Layout

```
odaiba_outbound/
├── pyproject.toml                     # declares the entry point
└── src/odaiba_outbound/
    ├── __init__.py                    # register() — the entry point target
    ├── odaiba_outbound.py         # the scenario class (BaseScenario)
    ├── configs.py                     # the scenario's config dataclass
    └── conf/scenario/odaiba_outbound/
        └── default.yaml               # a concrete scenario (YAML)
```

## Use it

```bash
# Install into the same environment as the framework.
uv pip install -e .

# Run the scenario — it is discoverable by name, no framework edits required.
uv run scenario scenario=odaiba_outbound/default map=nishishinjuku

# Batch/glob and CLI overrides work exactly like the built-ins:
uv run scenario scenario='odaiba_outbound/*' map=nishishinjuku
uv run scenario scenario=odaiba_outbound/default scenario.timeout_seconds=20
```

## Ship it as a container

`pack-scenario-image` builds an image holding this package, the framework and a
CARLA client pinned at build time:

```yaml
- uses: tier4/autoware_lanelet2_to_opendrive/.github/actions/pack-scenario-image@main
  with:
    scenario-package-path: odaiba_outbound
    image: ghcr.io/<owner>/odaiba-outbound
    carla-version: "0.10.0"
```

Pin a release tag instead of `main` for a reproducible framework version. See
the framework's *Container Image* documentation for the inputs and for building
the same image by hand.

## How it plugs in

`register()` in `__init__.py` calls `register_scenario(...)` and
`register_conf_dir(...)`; the `autoware_carla_scenario.scenarios` entry point in
`pyproject.toml` makes the `scenario` CLI discover it automatically at start-up.
