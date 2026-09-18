# Tasks Document

Phase A (tasks 1-9) is a pure refactor: TrafficManager keeps behaving exactly as it does
today, from behind the new seam, and the existing test suite is the acceptance criterion.
It is mergeable on its own. Phase B (tasks 10-18) adds SUMO. Phase C (19-21) is
documentation and CI.

**Phase A is done.** The suite is green (the two `test_maps.py` git-pinning failures are
pre-existing on `master` and unrelated), `ruff`, `ruff-format` and `mypy` pass, and
`traffic=none` / `traffic.options.port=…` / the legacy `traffic_manager.port` all resolve
through `build_traffic_backend`. Task 20's documentation was written with it rather than
held back, because a seam nobody can find is not a seam.

## Phase A — the seam (no behaviour change)

- [x] 1. Define the backend contract
  - File: `autoware_carla_scenario/src/autoware_carla_scenario/traffic/base.py` (new)
  - `TrafficContext`, `TrafficBackend` (ABC), `TrafficBackendUnavailable`,
    `TrafficBackendError`; move `LaneChangeDirection` and `TurnDirection` here
  - No CARLA or TraCI import, per the cheap-import rule `registry.py` follows
  - Purpose: one interface the runner and the entities talk to
  - _Leverage: `entity/tm_driving.py` (enums, protocols), `entity/ego.py` (lifecycle hook naming)_
  - _Requirements: 1.1, 1.3_

- [x] 2. Backend registry with entry-point discovery
  - File: `.../traffic/registry.py` (new)
  - `register_backend`, `get_backend_factory`, `available_backends`,
    `load_traffic_backend_plugins` over `autoware_carla_scenario.traffic_backends`
  - Purpose: select a backend by name, including third-party ones
  - _Leverage: `registry.py` (same structure, same error style)_
  - _Requirements: 2.3, 2.4_

- [x] 3. Configuration dataclasses
  - Files: `.../traffic/config.py` (new), `.../scenario_config.py` (extend `__all__`)
  - `TrafficConfig`, `TrafficManagerBackendConfig`, `SumoBackendConfig`,
    `AmbientTrafficConfig`, each with a `from_mapping` that rejects unknown keys
  - Legacy `traffic_manager.port` resolves into `TrafficManagerBackendConfig.port`
  - Purpose: a public, validated config surface external packages can import
  - _Leverage: `driver/base.py::_checked`, `scenario_config.py`_
  - _Requirements: 2.2, 5.4_

- [x] 4. TrafficManager backend
  - File: `.../traffic/traffic_manager.py` (new)
  - Move the sync-mode + seed block (`scenario_runner.py:577-582`), the autopilot loop
    (`scenario_runner.py:646-657`), and the manoeuvre bodies and geometry helpers from
    `entity/tm_driving.py`
  - Purpose: today's behaviour, behind the interface
  - _Leverage: `entity/tm_driving.py` (moved verbatim), `constants.py::DEFAULT_TM_PORT`_
  - _Requirements: 1.1, 1.2_

- [x] 5. Entities delegate instead of calling the TrafficManager
  - Files: `.../traffic/driven.py`, `.../entity/vehicle_entity.py`, `.../entity/ego.py`
  - `BackendDriven` mixin holding `_traffic_backend`, whose `set_client()` builds a
    `TrafficManagerBackend`; `entity/tm_driving.py` and `TrafficManagerDriven` deleted
  - Purpose: an entity asks for an intent and does not know what performs it
  - _Leverage: existing `LaneChanging` / `TurningAtJunctions` protocols (unchanged, so no action edits)_
  - _Requirements: 1.1, 5.1_

- [x] 6. Runner drives the backend
  - File: `.../scenario_runner.py`
  - Build `TrafficContext`, call `prepare()` before `setup()`, `start()` where the
    autopilot loop was, `tick()` beside `ego.on_tick()`, `close()` in the `finally` block
  - Ownership skip set replaces the ad-hoc `skip_ids`
  - Purpose: no backend-specific code left in the loop
  - _Leverage: existing lifecycle ordering and `_release_vehicles` / `_hold_vehicles_still`_
  - _Requirements: 1.1, 1.4, 5.1_

- [x] 7. Scenario hands registered entities to the backend
  - File: `.../scenario_base.py` (`register_entity`, `set_client`)
  - `entity.set_traffic_backend(backend)` alongside the existing `set_client`
  - Purpose: an authored NPC's intents reach whatever drives it
  - _Leverage: `entity/registry.py`_
  - _Requirements: 5.2_

- [x] 8. Hydra config group and CLI selection
  - Files: `.../examples/conf/traffic/traffic_manager.yaml` (new),
    `.../examples/conf/config.yaml` (defaults list), `.../examples/run.py`
    (`build_traffic_backend`, mirroring `build_ego_entity`)
  - Purpose: `traffic=<name>` selects the backend; omitting it keeps today's behaviour
  - _Leverage: `examples/run.py::build_ego_entity`_
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 9. Phase A tests
  - Files: `test/carla_scenario/test_traffic_registry.py`,
    `test_traffic_backend_contract.py`, `test_traffic_manager_backend.py` (new)
  - Contract suite (lifecycle order, idempotent `close`, intents never raise), registry
    errors, legacy `traffic_manager.port` fallback; existing suite must pass untouched
  - Purpose: prove the refactor changed nothing observable
  - _Leverage: `test/carla_scenario/test_driven.py`, `pytest_fixtures.py`_
  - _Requirements: 1.2, 1.3, 2.2_

## Phase B — SUMO

Interface questions Phase A deliberately left open, raised by the Phase A
review and to be settled with the first co-simulation backend rather than
guessed at now:

- **No failure channel out of `tick()`.** Requirement 3 wants a backend that dies
  mid-run to end the scenario as a failure attributed to it, but `tick()` must
  not raise. Add a `failed` / `health()` member, or a documented exception the
  runner catches, when task 16 lands. Related: `ScenarioQueue.run_all` catches
  bare `Exception` and retries, so a `TrafficBackendUnavailable` ("SUMO is not
  installed") would today be retried `cooldown_max_retries` times — let that
  error escape the retry loop.
- **`adopt()` has no inverse.** An NPC destroyed mid-run, and `clear_entities()`
  between queued scenarios, leave a backend publishing vehicles that no longer
  exist. Either add `abandon(entity)` or keep the rule `base.py` now states —
  `close()` forgets everything adopted.
- **`adopt()`'s precondition is convention, not contract.** The ego is adopted
  after its actor exists; an NPC is adopted wherever the scenario calls
  `register_entity`. SUMO needs the CARLA actor id at adopt time, so make the
  precondition explicit (or pass the actor) in task 16.
- **Ownership is stated three times per entity.** `use_autopilot`, the
  `change_lane` / `turn_at_junction` overrides on `AutowareEgoEntity` and
  `CarlaDriverEntity`, and the runner's `skip_actor_ids`. One property on the
  entity (`driven_by_traffic_backend`), recorded by `adopt()`, would let
  `start()` build its own skip set and collapse the overrides — design.md's
  Error Handling §6 already promises the ownership table.

- [ ] 10. Optional dependency extra
  - File: `autoware_carla_scenario/pyproject.toml`
  - `[project.optional-dependencies] sumo = ["eclipse-sumo==1.26.0", "traci>=1.26",
    "sumolib>=1.26", "ll2sumo @ git+https://github.com/autowarefoundation/lanelet2_to_sumo@<pinned-ref>"]`;
    lock with `uv lock`
  - `ll2sumo` is not on PyPI, so it is pinned by git ref; settle two things first — that a
    git dependency is acceptable here (it cannot come from an index mirror), and the
    upstream repository's licence, which has no `LICENSE` file at the time of writing
  - Vendoring the converter, or asking upstream to publish it, are the alternatives if
    either answer is no
  - Purpose: SUMO and the converter arrive without a compiler, and only when asked for
  - _Requirements: 3.5, 4.1_

- [ ] 11. The network in play: Lanelet2 → SUMO, cached, or the one the config names
  - File: `.../traffic/sumo/net.py` (new)
  - `ensure_sumo_network(config, context) -> SumoNetwork`, covering both routes:
    - **Route 1**: `ll2sumo.convert_map(input_path=context.lanelet2_path, out_dir=cache_dir,
      lane_change_mode=..., signal_mode=...)`; cache key = hash(`.osm` content + options);
      keep `net_path`, `signal_mapping_path` and the `randomtrips.safe.*` prefix it returns
    - **Route 2**: `config.net_path` short-circuits conversion entirely — file used as it
      sits, nothing cached, `ll2sumo` not even imported
  - Both routes read `<location netOffset= projParameter=>` off the net with `sumolib`, so
    the geo-reference is never assumed; a projection mismatch against the Lanelet2 map is an
    error, an offset mismatch a warning, `trust_net_georeference` overrides
  - A supplied net with no signal mapping logs the degradation once
  - Purpose: one network, two honest ways to get it
  - _Leverage: `maps.resolve_map_paths`, `maps/cache.py::GitMapCache.derived_dir`_
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4b.1, 4b.2, 4b.3, 4b.4, 4b.5_

- [ ] 12. Ambient demand generation
  - File: `.../traffic/sumo/demand.py` (new)
  - `randomTrips.py` driven from `AmbientTrafficConfig`, seeded, cached beside the net,
    using `ll2sumo`'s `randomtrips.safe.*` weights (`--weights-prefix`) so disconnected and
    dead-end edges are not used as sources or destinations; an explicit `route_path`
    short-circuits it, and is required when the network came from `net_path`
  - `randomTrips.py` is resolved from the SUMO tools directory
    (`sumo.SUMO_HOME/tools` with the wheel installed, else `$SUMO_HOME/tools`)
  - Purpose: reproducible flow without hand-written route files, and without jams
  - _Requirements: 3.4_

- [ ] 13. Frame conversion CARLA ↔ SUMO
  - File: `.../coordinate/sumo.py` (new) or `traffic/sumo/frames.py`
  - Conversion built from the net's `<location>` header and the Lanelet2 map's projection,
    which is the frame `MapManager` already holds; round-trip property test
  - Purpose: one place that knows the two frames differ
  - _Leverage: `coordinate/transform.py`, `coordinate/poses.py`, `coordinate/map_manager.py`_
  - _Requirements: 3.2, 3.3, 4b.2_

- [ ] 14. The co-simulation loop
  - File: `.../traffic/sumo/sync.py` (new)
  - `TraciLike` / `WorldLike` protocols; `publish_owned`, `step`, `apply_to_carla`,
    `sync_traffic_lights`; TraCI subscriptions and CARLA batch commands, not per-vehicle calls
  - Traffic lights join on Lanelet2 ids: read `lanelet_signal_to_sumo_links` from the
    `signal_id_mapping.json` the network came with, and write each CARLA light's state to
    its `tlLogic id + linkIndex` with `setRedYellowGreenState` (or the reverse under
    `traffic_light_authority: sumo`).  No mapping — a supplied network without one — means
    signals are left unsynchronised, said once
  - Purpose: the exchange, testable without either simulator
  - _Leverage: `driver/base.py` (abstract-client-for-testability precedent), `coordinate/snap.py`,
    `coordinate/traffic_light.py` for the CARLA half of the same join_
  - _Requirements: 3.1, 3.2, 3.3, 5.3, 4.4, 4b.4_

- [ ] 15. Vehicle type mapping
  - Files: `.../traffic/sumo/types.py`, `.../traffic/sumo/vtypes.json` (new)
  - SUMO vType → CARLA blueprint with a documented default table and a config override
  - Purpose: a SUMO truck is not mirrored as a hatchback
  - _Requirements: 3.2_

- [ ] 16. The SUMO backend
  - File: `.../traffic/sumo/backend.py` (new)
  - Process lifecycle (`sumo` / `sumo-gui` / `libsumo`), `prepare` → `ensure_sumo_network`
    + demand + start, `start` → publish CARLA-owned vehicles, `tick` → one step, `close` →
    destroy mirrored actors and close TraCI; intents via `changeLane` / `setRoute`
  - The backend never builds a network itself: whichever route produced it, it receives a
    `SumoNetwork` and starts SUMO on that
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
  - Fake TraCI and fake world; the contract suite from task 9 parameterized over the SUMO
    backend
  - `test_sumo_net.py` covers both routes: Route 1 cache behaviour and conversion-failure
    reporting with `ll2sumo` faked, Route 2 short-circuiting (the fake converter is never
    called), header-derived transforms, projection mismatch refused, offset mismatch warned,
    `trust_net_georeference` honoured, missing signal mapping degraded loudly
  - One `slow`-marked test runs the real `ll2sumo` on the `nishishinjuku` fixture's `.osm`
    and asserts the network parses with `sumolib`; its output is then the Route 2 input, so
    one conversion covers both routes
  - Purpose: CI coverage without a CARLA or SUMO server
  - _Leverage: task 9's contract suite_
  - _Requirements: 3.1, 3.2, 3.4, 4.1, 4.2, 4.3, 4b.1, 4b.2, 4b.3, 4b.4_

## Phase C — reporting, docs, CI

- [ ] 19. Backend recorded in the result
  - Files: `.../scenario_runner.py`, result model / viewer
  - `backend.describe()` (name, seed, versions) written with the run metadata and shown
  - Purpose: a result says what drove its traffic
  - _Requirements: 5.4_

- [x] 20. Documentation
  - Files: `autoware_carla_scenario/docs/traffic_backends.md` (new),
    `docs/architecture.md` (traffic section and lifecycle diagrams), `docs/api.md`,
    `mkdocs.yml` (nav), the package README
  - Follows `docs/driver_interface.md`'s shape: architecture, how to run, config table,
    lifecycle table, Python API, writing your own backend
  - Written with Phase A rather than held for Phase C: the seam is the deliverable, and
    one nobody can find is not a seam
  - _Requirements: 2.4_

- [ ] 21. CI
  - File: `.github/workflows/*`
  - Unit + fake-based tests on every PR; the `slow` `ll2sumo` conversion test in the
    existing suite;
    the CARLA+SUMO end-to-end left to the manual/integration job
  - _Requirements: 3.1_
