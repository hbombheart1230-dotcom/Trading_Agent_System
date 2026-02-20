# Runtime Profile Runbook (M28-1)

- Last updated: 2026-02-20
- Scope: runtime profile validation before scheduler/worker startup.

## 1. Profile Variables

Set profile options in `.env` (or environment):

```env
RUNTIME_PROFILE=dev
M28_PROFILE_STRICT=false
```

Profiles:
- `dev`
- `staging`
- `prod`

## 2. Validate Active Profile

```powershell
python scripts/check_runtime_profile.py --profile dev --env-path .env --json
```

Return codes:
- `0`: profile validation pass
- `3`: profile validation fail

## 3. Run M28-1 Scaffold Gate

```powershell
python scripts/run_m28_runtime_profile_scaffold_check.py --json
```

This gate validates seeded `dev/staging/prod` profiles with strict mode.

## 4. Validation Policy Summary

- `dev/staging`:
  - default `KIWOOM_MODE=mock`
  - default `EXECUTION_ENABLED=false`
- `prod`:
  - expects `KIWOOM_MODE=real`
  - requires:
    - `KIWOOM_APP_KEY`
    - `KIWOOM_APP_SECRET`
    - `KIWOOM_ACCOUNT_NO`
  - if `EXECUTION_ENABLED=true`, then `ALLOW_REAL_EXECUTION=true` is mandatory

## 5. Triage

- Missing required key:
  - populate profile-specific env keys and rerun gate.
- mode mismatch (`KIWOOM_MODE`):
  - align with target profile (`mock` for dev/staging, `real` for prod).
- execution guard mismatch:
  - if execution is enabled, set `ALLOW_REAL_EXECUTION=true` explicitly.
