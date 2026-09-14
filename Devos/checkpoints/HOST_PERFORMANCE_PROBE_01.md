# HOST_PERFORMANCE_PROBE_01

Status: accepted local checkpoint

## Objective

Give DevOS a bounded, read-only, on-command host performance probe that does not depend on the AIOS daemon or arbitrary shell execution.

## Deliverables

- `runtime/host_performance.py`
- `schemas/host-performance.schema.json`
- `tests/test_host_performance.py`
- manifest registration as `host_performance`

## Command

```text
python Devos/runtime/host_performance.py snapshot --output Devos/state/host-performance-latest.json
```

Optional controls:

- `--sample-ms 50..5000`
- repeatable `--root <path>` for explicit disk targets
- `--compact` for compact JSON

## Snapshot contract

The probe emits `devos.host_performance.v1` with UTC capture time, host/platform identity, sampled CPU use, logical CPU count, load average when available, physical-memory use, disk capacity/use, uptime, process count, derived pressure class, warnings, and provenance.

Pressure is advisory only: NORMAL below 70%, ELEVATED at 70%, HIGH at 85%, CRITICAL at 95%, using the highest available CPU/memory/disk utilization value.

## Safety and authority

- stdlib-only
- read-only host observation
- no `shell=True`
- no arbitrary command/argv surface
- Windows process count uses fixed `tasklist /FO CSV /NH` argv with a five-second timeout
- snapshot writes are atomic when `--output` is supplied
- `authority_effect` is always `NONE`
- generated snapshots are instance runtime state and are not distribution defaults

## Validation

Local tests passed:

- snapshot contract
- atomic JSON output round-trip
- pressure thresholds

The probe was also executed successfully in the implementation environment and returned a valid snapshot with no warnings.
