# M25-4: Alert Policy Env Profile and Runbook

- Date: 2026-02-17
- Goal: make alert thresholds operational by wiring policy defaults to `.env` and documenting operator run steps.

## Scope (minimal)

1. Allow alert policy defaults to come from `.env` profile variables.
2. Keep CLI flags as highest-priority overrides.
3. Document practical run commands and recommended baseline thresholds.

## Implemented

- File: `scripts/check_alert_policy_v1.py`
  - Loads `.env` via `load_env_file(".env")` before parsing args.
  - Uses env-backed default thresholds:
    - `ALERT_POLICY_FAIL_ON`
    - `ALERT_POLICY_LLM_SUCCESS_RATE_MIN`
    - `ALERT_POLICY_LLM_CIRCUIT_OPEN_RATE_MAX`
    - `ALERT_POLICY_EXECUTION_BLOCKED_RATE_MAX`
    - `ALERT_POLICY_EXECUTION_APPROVED_EXECUTED_GAP_MAX`
    - `ALERT_POLICY_API_429_RATE_MAX`

- File: `scripts/run_m25_closeout_check.py`
  - Loads `.env` before parser construction.
  - Uses `ALERT_POLICY_FAIL_ON` as default closeout fail mode.

- File: `config/.env.example`
  - Added commented alert policy env variables.

- File: `config/env_example`
  - Added commented alert policy env variables.

- File: `tests/test_m25_2_alert_policy_threshold_gate.py`
  - Added env-default override regression.
  - Added `.env` loader integration regression.

## Safety Notes

- This milestone changes only observability policy configuration defaults.
- Runtime decision/execution flow remains unchanged.
