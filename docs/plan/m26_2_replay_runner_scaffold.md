# M26-2: Replay Runner Scaffold

- Date: 2026-02-20
- Goal: provide a deterministic replay runner over M26 fixed dataset execution timeline.

## Scope (minimal)

1. Add one replay script that reads fixed dataset execution files (`intents`, `order_status`, `fills`).
2. Emit day-filtered replay summary metrics for operator/evaluation pipelines.
3. Add pass/fail regression tests.

## Implemented

- File: `scripts/run_m26_replay_runner.py`
  - Validates required dataset files:
    - `manifest.json`
    - `execution/intents.jsonl`
    - `execution/order_status.jsonl`
    - `execution/fills.jsonl`
  - Supports `--day` filter (UTC) for deterministic replay slicing.
  - Produces replay summary:
    - `replayed_intent_total`, `executed_intent_total`, `blocked_intent_total`, `pending_intent_total`
    - `fill_qty_total`, `fill_notional_total`
    - `replay_latency_sec` summary (`count/avg/p50/p95/max`)
  - Returns `rc=3` on contract failure or empty replay slice.

- File: `tests/test_m26_2_replay_runner.py`
  - Added seeded pass-case test (integrated with M26-1 scaffold).
  - Added fail-case tests:
    - day filter excludes all events
    - required files missing

## Safety Notes

- Replay runner is read-only against dataset files.
- No runtime trading path is affected by this milestone.
