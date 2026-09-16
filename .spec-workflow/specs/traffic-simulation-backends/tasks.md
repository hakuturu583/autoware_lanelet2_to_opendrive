# Tasks Document

Phase A (tasks 1-9) is a pure refactor: TrafficManager keeps behaving exactly as it does
today, from behind the new seam, and the existing test suite is the acceptance criterion.
It is mergeable on its own. Phase B (tasks 10-18) adds SUMO. Phase C (19-21) is
documentation and CI.

## Phase A — the seam (no behaviour change)

- [ ] 1. Define the backend contract
  - File: `autoware_carla_scenario/src/autoware_carla_scenario/traffic/base.py` (new)
  - `TrafficContext`, `TrafficBackend` (ABC), `TrafficBackendUnavailable`,
    `TrafficBackendError`; move `LaneChangeDirection` and `TurnDirection` here
  - No CARLA or TraCI import, per the cheap-import rule `registry.py` follows
  - Purpose: one interface the runner and the entities talk to
  - _Leverage: `entity/tm_driving.py` (enums, protocols), `entity/ego.py` (lifecycle hook naming)_
  - _Requirements: 1.1, 1.3_

- [ ] 2. Backend registry with entry-point discovery
  - File: `.../traffic/registry.py` (new)
  - `register_backend`, `get_backend_factory`, `available_backends`,
    `load_traffic_backend_plugins` over `autoware_carla_scenario.traffic_backends`
  - Purpose: select a backend by name, including third-party ones
  - _Leverage: `registry.py` (same structure, same error style)_
  - _Requirements: 2.3, 2.4_

- [ ] 3. Configuration dataclasses
  - Files: `.../traffic/config.py` (new), `.../scenario_config.py` (extend `__all__`)
  - `TrafficConfig`, `TrafficManagerBackendConfig`, `SumoBackendConfig`,
    `AmbientTrafficConfig`, each with a `from_mapping` that rejects unknown keys
  - Legacy `traffic_manager.port` resolves into `TrafficManagerBackendConfig.port`
  - Purpose: a public, validated config surface external packages can import
  - _Leverage: `driver/base.py::_checked`, `scenario_config.py`_
  - _Requirements: 2.2, 5.4_

- [ ] 4. TrafficManager backend
  - File: `.../traffic/traffic_manager.py` (new)
  - Move the sync-mode + seed block (`scenario_runner.py:577-582`), the autopilot loop
    (`scenario_runner.py:646-657`), and the manoeuvre bodies and geometry helpers from
    `entity/tm_driving.py`
  - Purpose: today's behaviour, behind the interface
  - _Leverage: `entity/tm_driving.py` (moved verbatim), `constants.py::DEFAULT_TM_PORT`_
  - _Requirements: 1.1, 1.2_

- [ ] 5. Entities delegate instead of calling the TrafficManager
  - Files: `.../entity/tm_driving.py`, `.../entity/vehicle_entity.py`, `.../entity/ego.py`
  - `BackendDriven` mixin holding `_traffic_backend`; `TrafficManagerDriven` kept as a
    deprecated subclass whose `set_client()` builds a `TrafficManagerBackend`
  - Purpose: an entity asks for an intent and does not know what performs it
  - _Leverage: existing `LaneChanging` / `TurningAtJunctions` protocols (unchanged, so no action edits)_
  - _Requirements: 1.1, 5.1_

- [ ] 6. Runner drives the backend
  - File: `.../scenario_runner.py`
  - Build `TrafficContext`, call `prepare()` before `setup()`, `start()` where the
    autopilot loop was, `tick()` beside `ego.on_tick()`, `close()` in the `finally` block
  - Ownership skip set replaces the ad-hoc `skip_ids`
  - Purpose: no backend-specific code left in the loop
  - _Leverage: existing lifecycle ordering and `_release_vehicles` / `_hold_vehicles_still`_
  - _Requirements: 1.1, 1.4, 5.1_

- [ ] 7. Scenario hands registered entities to the backend
  - File: `.../scenario_base.py` (`register_entity`, `set_client`)
  - `entity.set_traffic_backend(backend)` alongside the existing `set_client`
  - Purpose: an authored NPC's intents reach whatever drives it
  - _Leverage: `entity/registry.py`_
  - _Requirements: 5.2_

- [ ] 8. Hydra config group and CLI selection
  - Files: `.../examples/conf/traffic/traffic_manager.yaml` (new),
    `.../examples/conf/config.yaml` (defaults list), `.../examples/run.py`
    (`build_traffic_backend`, mirroring `build_ego_entity`)
  - Purpose: `traffic=<name>` selects the backend; omitting it keeps today's behaviour
  - _Leverage: `examples/run.py::build_ego_entity`_
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 9. Phase A tests
  - Files: `test/carla_scenario/test_traffic_registry.py`,
    `test_traffic_backend_contract.py`, `test_traffic_manager_backend.py` (new)
  - Contract suite (lifecycle order, idempotent `close`, intents never raise), registry
    errors, legacy `traffic_manager.port` fallback; existing suite must pass untouched
  - Purpose: prove the refactor changed nothing observable
  - _Leverage: `test/carla_scenario/test_tm_driving.py`, `pytest_fixtures.py`_
  - _Requirements: 1.2, 1.3, 2.2_

## Phase B — SUMO

- [ ] 10. Optional dependency extra
  - File: `autoware_carla_scenario/pyproject.toml`
  - `[project.optional-dependencies] sumo = ["eclipse-sumo>=1.20", "traci>=1.20", "sumolib>=1.20"]`;
    lock with `uv lock`
  - Purpose: SUMO arrives as a wheel, and only when asked for
  - _Requirements: 3.5_

- [ ] 11. OpenDRIVE → SUMO network, cached
  - File: `.../traffic/sumo/net.py` (new)
  - `ensure_sumo_net(xodr, cache_dir, options)`; cache key = hash(xodr content + options);
    `netconvert` stderr surfaced on failure
  - Purpose: the scenario's own map becomes the SUMO network, once
  - _Leverage: `maps/opendrive.py::ensure_xodr`, `maps/cache.py::GitMapCache.derived_dir`_
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 12. Ambient demand generation
  - File: `.../traffic/sumo/demand.py` (new)
  - `randomTrips.py` driven from `AmbientTrafficConfig`, seeded, cached beside the net;
    an explicit `route_path` short-circuits it
  - Purpose: reproducible flow without hand-written route files
  - _Requirements: 3.4_

- [ ] 13. Frame conversion CARLA ↔ SUMO
  - File: `.../coordinate/sumo.py` (new) or `traffic/sumo/frames.py`
  - Conversion given the netconvert offset settings; round-trip property test
  - Purpose: one place that knows the two frames differ
  - _Leverage: `coordinate/transform.py`, `coordinate/poses.py`_
  - _Requirements: 3.2, 3.3_

- [ ] 14. The co-simulation loop
  - File: `.../traffic/sumo/sync.py` (new)
  - `TraciLike` / `WorldLike` protocols; `publish_owned`, `step`, `apply_to_carla`,
    `sync_traffic_lights`; TraCI subscriptions and CARLA batch commands, not per-vehicle calls
  - Purpose: the exchange, testable without either simulator
  - _Leverage: `driver/base.py` (abstract-client-for-testability precedent), `coordinate/snap.py`_
  - _Requirements: 3.1, 3.2, 3.3, 5.3_

- [ ] 15. Vehicle type mapping
  - Files: `.../traffic/sumo/types.py`, `.../traffic/sumo/vtypes.json` (new)
  - SUMO vType → CARLA blueprint with a documented default table and a config override
  - Purpose: a SUMO truck is not mirrored as a hatchback
  - _Requirements: 3.2_

- [ ] 16. The SUMO backend
  - File: `.../traffic/sumo/backend.py` (new)
  - Process lifecycle (`sumo` / `sumo-gui` / `libsumo`), `prepare` → net + demand + start,
    `start` → publish CARLA-owned vehicles, `tick` → one step, `close` → destroy mirrored
    actors and close TraCI; intents via `changeLane` / `setRoute`
  - Purpose: the second backend
  - _Leverage: tasks 11-15; `server.py::CarlaServerManager` for subprocess lifecycle style_
  - _Requirements: 3.1, 3.2, 3.3, 3.5, 5.1_

- [ ] 17. Config group and registration
  - Files: `.../examples/conf/traffic/sumo.yaml` (new), `traffic/__init__.py`
  - Purpose: `uv run scenario traffic=sumo` works end to end
  - _Requirements: 2.1_

- [ ] 18. Phase B tests
  - Files: `test/carla_scenario/test_sumo_net.py`, `test_sumo_sync.py`,
    `test_sumo_backend.py` (new)
  - Fake TraCI and fake world; one `slow`-marked real-`netconvert` test on the
    `nishishinjuku` fixture; the contract suite from task 9 parameterized over the SUMO backend
  - Purpose: CI coverage without a CARLA or SUMO server
  - _Leverage: task 9's contract suite_
  - _Requirements: 3.1, 3.2, 3.4, 4.1_

## Phase C — reporting, docs, CI

- [ ] 19. Backend recorded in the result
  - Files: `.../scenario_runner.py`, result model / viewer
  - `backend.describe()` (name, seed, versions) written with the run metadata and shown
  - Purpose: a result says what drove its traffic
  - _Requirements: 5.4_

- [ ] 20. Documentation
  - Files: `autoware_carla_scenario/docs/traffic_backends.md` (new),
    `docs/architecture.md` (traffic section), `mkdocs.yml` (nav), both READMEs
  - Follow `docs/driver_interface.md`'s shape: architecture, how to run, config table,
    Python API, writing your own backend
  - _Requirements: 2.4_

- [ ] 21. CI
  - File: `.github/workflows/*`
  - Unit + fake-based tests on every PR; the `slow` `netconvert` test in the existing suite;
    the CARLA+SUMO end-to-end left to the manual/integration job
  - _Requirements: 3.1_
