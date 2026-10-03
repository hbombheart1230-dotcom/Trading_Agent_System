# Development Evidence Index

## Purpose

This index maps historical claims to repository evidence. It is intentionally
compact so `development_history.md` can explain evolution without embedding
every diff.

## Evidence Ranking

1. Git commit and diff at the introduction point
2. Source plus deterministic test at the same or later commit
3. Contemporaneous architecture/plan document
4. Current AS-IS documentation verified against source
5. Retrospective patch note or dated review

Agent attribution requires explicit provenance and does not inherit the ranking
of a technical claim.

## Baseline Evidence

| Claim | Evidence | Confidence |
| --- | --- | --- |
| Source baseline | `6aa4e398e2e1c33482cab3dbf2518e7b03c18a10` | VERIFIED |
| Baseline date | commit timestamp and approved baseline contract, `2026-08-31` | VERIFIED |
| Full regression | `2701 passed, 1 skipped` at `6aa4e39` | VERIFIED |
| Branch state | `codex/observability-20260824`, remote synchronized | VERIFIED |
| Main divergence | 9 commits ahead, 0 behind at investigation | VERIFIED |
| Pre-Claude status | approved provenance baseline purpose | VERIFIED |

## Milestone Commit Index

| Period | Milestone | Representative commits | Principal paths | Confidence |
| --- | --- | --- | --- | --- |
| Pre-Git | M1-M13 inferred foundation | first visible at `46934dc` | `docs/plan/archive`, initial code tree | SUPPORTED / UNCERTAIN chronology |
| 2026-02-12 | V6 architecture snapshot | `46934dc` | `README.md`, `graphs`, `libs`, `tests` | VERIFIED |
| 2026-02-14/15 | M20 LLM observability | `3a08fe0`, `e0ad92e`, `c4e0b6d`, `ca4dd9b` | Strategist provider, EventLog, reports | VERIFIED |
| 2026-02-15 | M21 canonical Commander | `5fc215d`, `9327d7e`, `aead984`, `b2d5b98` | `graphs/commander_runtime.py` | VERIFIED |
| 2026-02-15/16 | M22 skill-native Scanner/Monitor | `64922e2`, `c6e4920`, `82e974d` | Scanner, Monitor, skills | VERIFIED |
| 2026-02-17 | M23 resilience | `4fb321a`, `fcc94f1`, `c17ac2a` | resilience state, Commander, Strategist | VERIFIED |
| 2026-02-17 | M24 Intent persistence | `049b43f`, `917862d`, `26f3b8b`, `588d4e5` | `libs/supervisor/intent_state_store.py` | VERIFIED |
| 2026-02-17 | M25 metrics/alerts | `8cb1e2e`, `c536d89`, `7a595a6`, `6d4fee9` | metrics, alerting, ops | VERIFIED |
| 2026-02-20 | M26 evaluation scaffold | `660fea3`, `36ecfb5`, `5702872`, `16c9130` | dataset, scorecard, promotion gates | VERIFIED |
| 2026-02-20 | M27 portfolio controls | `71c37a8`, `b9bc3eb`, `ac15aff` | portfolio allocation/guards | VERIFIED |
| 2026-02-20/21 | M28 lifecycle/deployment | `b106cd2`, `bb7d1fd`, `22409df` | runtime profile, deployment | VERIFIED |
| 2026-02-21 | M29/M30 governance | `a757854`, `ac8ae83` | feature/monitor/governance/signoff | VERIFIED |
| 2026-02-21 to 03-08 | M31 operation | `f20826a`, `8d3ea93`, `e8bba4c`, `6ba1414` | runtime, scheduler, readiness | VERIFIED |
| 2026-03-10/13 | Role and trace alignment | `a7def76`, `c97a8e8`, `7a2e68d`, `5efe95e` | agents, Reporter, memory | VERIFIED |
| 2026-03-18 | Canonical events/artifacts | `f970488`, `4381491` | canonical schema/artifact/contracts | VERIFIED |
| 2026-04-02/21 | Policy-aware ownership | `d3d8078`, `f5f326a`, `7d26984` | alignment, truth, policy, memory | VERIFIED |
| 2026-05-15/21 | Modular refactor and Q1-Q7 | `cf10d1c`, `bc150a6` | runtime/report helpers, tactics | VERIFIED |
| 2026-06 | Q8/Q9 evaluation | `ebddf7f`, `658a6d0`, `40b3c0d` | `docs/tactics`, `docs/evaluation` | VERIFIED / SUPPORTED dates |
| 2026-07 | Q13-Q18 | `0d80a6c`, `4fc3755`, `7bf5643` | evaluation, Q13/Q14, horizon | VERIFIED |
| 2026-07-30 to 08-13 | Offline alpha/horizon | `7bf5643`, `d5aaed6`, `8956a61`, `89f53fc` | research, diagnosis, memory | VERIFIED |
| 2026-08-14 | Read-only Web plane | `759eafa`, `fe15cf4` | `apps/api`, `apps/web`, docs | VERIFIED |
| 2026-08-21/24 | Research Board/integrity | `3aa9ece`, `d9e22a3`, `117ec6e` | alpha board, evaluation | VERIFIED |
| 2026-08-27/30 | Scheduled ops/deployment | `ffd57a4`, `8894416`, `f7dac2f` | scheduled intelligence, Web, Cloudflare | VERIFIED |
| 2026-08-31 | Q10/Q12 capture wiring | `6aa4e39` | controlled lanes, captures, integration tests | VERIFIED |

## Architecture Evidence

| Topic | Current evidence |
| --- | --- |
| System overview | `README.md` |
| Current runtime definition | `docs/alignment/02_current_system_definition_as_is.md` |
| Agent roles and handoffs | `docs/alignment/03_agent_roles_inputs_outputs_and_handoffs.md` |
| Canonical orchestrator | `graphs/commander_runtime.py` |
| Runtime entry | `scripts/run_session.py` |
| Current flow | `docs/architecture/system_flow.md` |
| Unified principles | `docs/unified_runtime_spec.md` |
| Agent contracts | `libs/contracts/agent_outputs.py`, `libs/strategies/contracts.py` |
| Canonical artifacts | `libs/runtime/canonical_artifacts.py` |
| Approval service | `libs/approval/service.py` |
| Persistent Intent state | `libs/supervisor/intent_state_store.py` |
| Execution guards | `graphs/nodes/execute_from_packet.py` |
| Artifact flow | `docs/canonical_artifact_flow.md` |
| Event schema | `docs/canonical_event_schema.md` |
| Read-only Web boundary | `docs/web_observability/README.md`, `deploy/compose/README.md` |

## Evaluation and Research Evidence

| Program | Authority/evidence |
| --- | --- |
| Q8 tactics | `docs/tactics/README.md`, `docs/tactics/q8_evaluation_contract.md` |
| Q9-Q18 | `docs/evaluation/README.md`, `docs/evaluation/q9_q18_operating_status_2026-08-05.md` |
| Q13/Q14 | `docs/q13/README.md`, `docs/q14/README.md`, `docs/q13_q14_validation/README.md` |
| Quant diagnosis | `docs/quant_trade_diagnosis/README.md` |
| Horizon | `docs/strategy_horizon_feedback/README.md` |
| Offline alpha | `docs/offline_alpha/README.md` |
| Alpha Research Board | `docs/offline_alpha/alpha_research_board_contract_2026-08-27.md` |
| Web observability | `docs/web_observability/README.md` |

## Attribution Evidence

| Claim | Evidence | Decision |
| --- | --- | --- |
| All commits use one Git author identity | `git shortlog -sne HEAD` | Git author cannot identify AI agent |
| M31 audit was performed by Codex | `docs/plan/m31_operational_readiness_audit_2026-03-08.md` | VERIFIED for that audit only |
| Codex-centered workflow from 2026-04-07 | `docs/dev/workflow.md`, introduced by `3a37f1c` | SUPPORTED |
| Codex coding guardrails | `docs/dev/codex_rules.md` | workflow evidence, not authorship proof |
| Claude pre-baseline contribution | no direct repository evidence found | UNKNOWN / do not claim |
| `codex/*` branch implies each commit was Codex-authored | branch name only | insufficient; UNCERTAIN |

## Patch-Note Evidence Caveats

`docs/trading_agent_patch_notes_detailed_update/patch_notes.json` is a useful
retrospective index, but at baseline:

- its first dates precede the first Git commit
- eight source references do not resolve in the current tree
- some entries summarize historical plans rather than commit-introduction dates
- the JSON ended at `2026-08-30`, while Markdown contained an 8/31 entry

Therefore patch notes can locate a topic but do not independently prove
chronology or AI attribution.

## Verification Rule for Future Audits

For every future architecture finding, record:

1. reviewed baseline/commit
2. exact source or contract location
3. reproducing test or artifact, when applicable
4. whether the finding is historical behavior, current AS-IS, target mismatch,
   or accepted debt
5. finding author and independent reviewer
6. confidence and final Human disposition
