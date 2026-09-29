# 2026-09-29 Pytest Artifact Hygiene (Permanent Fix)

## Scope

Test infrastructure only. No trading, UEF, or Docker semantics touched.

## Root cause

An earlier same-day fix made pytest's `--basetemp` unique per process (`.pytest-work-<pid>/`) to resolve a
concurrent-pytest collision, but kept it repo-relative and never deleted it at session end -- every
invocation left a directory behind permanently. A pre-existing cleanup tool
(`scripts/cleanup_pytest_artifacts.py`/`.ps1`/`.cmd`) already existed for exactly this, but nothing ever
called it automatically. Separately, two ~6-month-old orphaned `data/pytest-cache-files-*` directories
(pytest's own built-in cache-provider plugin, from a since-changed config) were found; both are git-ignored
and harmless, and one is stuck under a Windows ACL that resists both `chmod` and `icacls` from this
account -- left in place rather than force-escalating permissions on a shared host.

## Fix

`conftest.py::pytest_configure` now points `--basetemp` at an OS-temp, per-process directory
(`%TEMP%/Trading_Agent_System/pytest/basetemp-<pid>/`) -- never repo-relative -- and a merged
`pytest_sessionfinish` hook removes that session's own directory immediately once it finishes cleanly
(no test failures, no production-write violation). A failing/interrupted session's directory is kept for
inspection but swept by the next invocation's stale-PID sweep once its owning process is confirmed dead --
bounded, not indefinite. `pytest.ini`, `libs/core/path_isolation.py`, and `scripts/run_pytest.py`/`.ps1`
updated to match. Two confirmed-dead leaked `.pytest-work-<pid>` directories removed. New rule added to
`docs/ground_rules/AGENT_RULES.md` (Test Artifact Hygiene). New regression coverage in
`tests/test_pytest_artifact_hygiene.py`: three repeated real nested pytest sessions leave zero new
repo-local scratch; a successful session's basetemp is removed; a dead-PID stale directory is swept.

## Validation

Full affected regression set (268 tests) plus the 9-test heavy subset pass; `git status --short` after
every run shows no new untracked artifacts.
