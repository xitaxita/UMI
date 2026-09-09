# UMI — Development decisions

## D-001: Use pysurvive for Vive tracking

- **Status:** Accepted
- **Date:** 2026-09-07
- **Source:** The user explicitly requested `pysurvive` instead of OpenVR.
- **Decision:** Acquire Vive poses through libsurvive's high-level
  `pysurvive.SimpleContext` API. This node does not require SteamVR or OpenVR.
- **Impact:** The host needs libsurvive, pysurvive, suitable USB rules,
  lighthouse calibration, and connected Vive hardware.
- **Supersedes:** The initial task-level choice to use SteamVR/OpenVR.
- **Current evidence:** On 2026-09-08 the user reported that the live Vive pose
  is correct and has no observed problem. Path, TF, loss recovery, and timestamp
  suitability were not included in that report.

## D-002: Publish stationary-reference drift diagnostics (withdrawn)

- **Status:** Withdrawn on 2026-09-09
- **Date:** 2026-09-09
- **Source:** The user requested publication and RViz visualization of apparent
  position and velocity drift while the Vive is physically stationary.
- **Decision:** `vive_drift_monitor_node` uses the first pose, or a reset pose,
  as its reference. It publishes displacement, displacement magnitude,
  finite-difference linear/angular velocity, speed, and RViz arrow markers.
- **Interpretation constraint:** The node observes motion in tracking output; it
  cannot classify physical movement versus sensor drift. Values represent drift
  only when the operator keeps the tracker stationary.
- **Withdrawal:** After trying the combined launch, the user requested a rollback
  because the result was not useful enough. Drift-related nodes, topics, markers,
  dependencies, tests, configuration, and launch integration are removed for now.
