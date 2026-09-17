# Requirements Document

## Introduction

`autoware_carla_scenario` currently has exactly one source of surrounding traffic:
CARLA's built-in TrafficManager (TM). `ScenarioRunner` enables autopilot on every
vehicle actor except an opted-out ego, and every manoeuvre an NPC can be asked for
(`change_lane`, `turn_at_junction`) is a TrafficManager call made from the
`TrafficManagerDriven` mixin.

That is a good default for a handful of scripted NPCs, but it is the wrong tool for
dense, calibrated, demand-driven traffic. Microscopic traffic simulators —
[SUMO](https://eclipse.dev/sumo/) above all — model car-following, gap acceptance,
route choice and demand in ways TM does not, and are the accepted reference for traffic
flow. Autoware evaluation increasingly wants that: "does the stack merge into a
saturated flow at this intersection?" is a question about traffic, not about three
scripted cars.

This spec introduces a **traffic backend** seam: one named, pluggable component that
owns the non-ego traffic of a run. TrafficManager becomes its default implementation,
SUMO becomes the second, and a third-party simulator becomes possible without touching
the runner.

## Alignment with Product Vision

Every run in this workspace already names a Lanelet2 map — it is what the converter reads
and what Autoware plans on — and
[`lanelet2_to_sumo`](https://github.com/autowarefoundation/lanelet2_to_sumo) turns exactly
that file into a SUMO network. So the traffic model reads the same road network as the
stack under test rather than a second derivation of it, which makes this feature a natural
extension of the product rather than a parallel pipeline: one map, one scenario document,
one result format, several traffic models.

A run that already has a `.net.xml` — hand-tuned, or produced by another toolchain — names
it instead, so the converter is the default rather than a requirement.

It also repeats a pattern the package has already settled on twice — the pluggable
scenario registry (`registry.py`) and the swappable ego entity (`ego.entity` ∈
`autopilot | autoware | carla_driver`). Traffic is the third axis, and it is the only one
still hard-wired.

## Requirements

### Requirement 1 — Traffic backend abstraction

**User Story:** As a framework developer, I want the runner to drive traffic through one
named interface, so that adding a traffic simulator does not mean editing the tick loop.

#### Acceptance Criteria

1. WHEN `ScenarioRunner` runs a scenario THEN it SHALL delegate traffic startup, per-tick
   stepping and teardown to a single `TrafficBackend` object rather than calling
   `set_autopilot` or `get_trafficmanager` itself.
2. WHEN no traffic configuration is given THEN the runner SHALL select the TrafficManager
   backend, and the observable behaviour of every existing scenario SHALL be unchanged.
3. WHEN a backend is asked for a manoeuvre it cannot perform THEN it SHALL log a warning
   and leave the vehicle as it is, never raise into the tick loop.
4. IF a backend fails to start THEN the scenario SHALL fail with a message naming the
   backend and the reason, before any CARLA actor is spawned.

### Requirement 2 — Backend selection from configuration

**User Story:** As a scenario author, I want to pick the traffic model on the command
line, so that one scenario can be run against TrafficManager and against SUMO.

#### Acceptance Criteria

1. WHEN a run passes `traffic=sumo` THEN the SUMO backend SHALL drive that run's traffic.
2. WHEN a run passes no `traffic` group THEN the TrafficManager backend SHALL be used, and
   the existing `traffic_manager.port` key SHALL keep working unchanged.
3. WHEN a config names an unknown backend THEN the run SHALL fail with an error listing
   the registered names.
4. IF a third-party package advertises a backend through the
   `autoware_carla_scenario.traffic_backends` entry-point group THEN the name it registers
   SHALL be selectable exactly like a built-in one.

### Requirement 3 — SUMO co-simulation

**User Story:** As an evaluation engineer, I want SUMO to generate the ambient traffic of a
CARLA run, so that Autoware is tested against calibrated flow rather than scripted cars.

#### Acceptance Criteria

1. WHEN the SUMO backend starts THEN it SHALL step SUMO exactly once per `world.tick()`,
   with SUMO's step length equal to the world's `fixed_delta_seconds`.
2. WHEN SUMO spawns, moves or removes an ambient vehicle THEN a CARLA actor SHALL appear,
   follow and disappear with it within one tick.
3. WHEN the ego or a scenario-authored NPC moves in CARLA THEN its position SHALL be
   published into SUMO so that SUMO-driven vehicles react to it.
4. WHEN a run is repeated with the same seed and the same scenario THEN the ambient traffic
   SHALL be reproducible.
5. IF SUMO is not installed THEN selecting the backend SHALL fail with a message naming the
   optional dependency extra that provides it.

### Requirement 4 — Network derived from the scenario's own Lanelet2 map

**User Story:** As a scenario author, I want the SUMO network to come from the Lanelet2 map
the scenario already names, so that I do not maintain a second map by hand and the traffic
model reads the same road network Autoware plans on.

#### Acceptance Criteria

1. WHEN a run selects SUMO and names no network file THEN the backend SHALL derive a
   `.net.xml` from the same Lanelet2 `.osm` the run was given, using
   [`ll2sumo`](https://github.com/autowarefoundation/lanelet2_to_sumo).
2. WHEN the derived network for a Lanelet2 map and a set of conversion options already
   exists in the map cache THEN it SHALL be reused rather than regenerated.
3. WHEN the Lanelet2 map or the conversion options change THEN the derived network SHALL be
   regenerated.
4. WHEN the network is generated THEN the Lanelet2 → SUMO signal mapping the converter
   emits SHALL be kept with it, so that traffic-light synchronisation joins the two
   simulators on Lanelet2 ids rather than on geometry.

### Requirement 4b — A network the run supplies

**User Story:** As a scenario author, I want to run against a `.net.xml` I already have —
hand-tuned, produced by another toolchain, or generated once ahead of a sweep — so that the
converter is a default rather than a requirement.

#### Acceptance Criteria

1. IF a run names an explicit `net_path` THEN that file SHALL be used verbatim, and no
   conversion SHALL run.
2. WHEN a run names an explicit `net_path` THEN the CARLA ↔ SUMO transform SHALL be derived
   from that network's own `<location netOffset= projParameter=>` header, the same way it is
   for a generated one.
3. IF a supplied network's projection disagrees with the Lanelet2 map's THEN the run SHALL
   fail at startup naming both, unless the config explicitly says to trust the network.
4. IF a supplied network brings no signal mapping THEN the backend SHALL say once that
   traffic lights are not synchronised, rather than silently running them unsynchronised.
5. WHEN only a supplied network is used THEN the converter and its dependencies SHALL NOT
   be required to be installed.

### Requirement 5 — One authority per vehicle and per traffic light

**User Story:** As a scenario author, I want it to be unambiguous what drives each vehicle,
so that a scenario stays deterministic and reproducible.

#### Acceptance Criteria

1. WHEN a backend owns a vehicle THEN no other component SHALL command that vehicle, and in
   particular `set_autopilot` SHALL NOT be called on vehicles a non-TM backend owns.
2. WHEN a scenario registers an NPC entity THEN that entity SHALL remain CARLA-side and
   scenario-owned under every backend; only ambient traffic is the backend's to create.
3. WHEN traffic lights exist in both simulators THEN exactly one SHALL be authoritative,
   selected by configuration, and the other SHALL follow it.
4. WHEN a run finishes THEN the result record SHALL state which backend drove it and with
   which seed.

## Non-Functional Requirements

### Code Architecture and Modularity

- **Single Responsibility**: one module per backend under
  `src/autoware_carla_scenario/traffic/`; the runner holds no backend-specific branch.
- **Modular Design**: the TrafficManager specifics currently in
  `entity/tm_driving.py` and in `ScenarioRunner.run()` move behind the interface without
  changing what they do.
- **Dependency Management**: `traffic/base.py` and the registry SHALL import neither CARLA
  nor TraCI, so the editor and the config layer can import them cheaply — the rule
  `scenario_config.py` and `registry.py` already follow.
- **Clear Interfaces**: entities ask for *intents* (`change_lane`, `turn_at_junction`); the
  backend decides what the intent means. No action reaches for a simulator API.

### Performance

- The per-tick sync SHALL add no more than a few milliseconds at 20 Hz for ~100 vehicles;
  TraCI subscriptions (not per-vehicle getters) and CARLA batch commands are the means.
- Network generation SHALL happen once per map, cached, never inside the tick loop.

### Reliability

- A backend that dies mid-run SHALL end the scenario as a failure with its own message,
  not as a timeout.
- Teardown SHALL close the backend and remove every actor it created, including after an
  exception, so the next scenario in a batch starts clean.

### Usability

- Switching traffic model SHALL be a single Hydra override.
- Running without SUMO installed SHALL remain the default experience; no existing user
  gains a new mandatory dependency.
