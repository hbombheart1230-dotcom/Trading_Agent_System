# M28-1: Runtime Profile Scaffold

- Date: 2026-02-20
- Goal: establish deploy-target runtime profiles (`dev/staging/prod`) with deterministic env validation gates.

## Scope (minimal)

1. Define runtime profile defaults and required env keys.
2. Add a profile validation CLI for operator/scheduler preflight.
3. Add a reproducible M28-1 scaffold check script and regressions.

## Implemented

- File: `libs/runtime/runtime_profile.py`
  - Added profile spec and validation core:
    - `runtime_profile_spec(profile)`
    - `profile_effective_env(profile, environ)`
    - `validate_runtime_profile(profile, environ, strict=...)`
  - Profiles:
    - `dev`
    - `staging`
    - `prod`
  - Core checks:
    - required env presence by profile
    - mode/guard consistency (`KIWOOM_MODE`, `EXECUTION_ENABLED`, `ALLOW_REAL_EXECUTION`)
    - strict-mode warning escalation

- File: `scripts/check_runtime_profile.py`
  - CLI for runtime profile validation.
  - Options:
    - `--profile {dev,staging,prod}`
    - `--env-path`
    - `--strict`
    - `--json`
  - Exit code:
    - `0`: pass
    - `3`: validation fail

- File: `scripts/run_m28_runtime_profile_scaffold_check.py`
  - Seeds deterministic env profiles for dev/staging/prod.
  - Runs `check_runtime_profile.py` across all profiles in strict mode.
  - Supports failure injection (`--inject-fail`) by removing required prod secret.

- File: `tests/test_m28_1_runtime_profile_scaffold.py`
  - Added profile validation and scaffold-check pass/fail regressions.
  - Added script entrypoint import-resolution regression.

## Operator Usage

```bash
python scripts/check_runtime_profile.py --profile dev --env-path .env --json
python scripts/run_m28_runtime_profile_scaffold_check.py --json
```

## Notes for M28-2

- Next step should wire this profile gate into startup/scheduler entrypoints so runtime refuses invalid profile boots.
