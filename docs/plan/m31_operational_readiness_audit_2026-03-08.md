# M31 Operational Readiness Audit (2026-03-08)

- Scope: operational validation only (no feature additions).
- Basis: repository code + generated artifacts (`reports/*`) + env/runtime policy snapshot.
- Auditor: Codex

## Final Verdict

- Initial Readiness (pre-fix snapshot): **NOT_READY**
- Current Readiness (post-fix snapshot, 2026-03-08): **READY**

What changed:
1. `.env` updated: `APPROVAL_MODE=manual`
2. readiness gate re-run passed with all required checks

Evidence:
- pre-fix: `reports/m31_mock_exam_readiness/m31_mock_exam_readiness_2026-03-07.json`
- post-fix: `reports/m31_mock_exam_readiness/m31_mock_exam_readiness_2026-03-08.json`
- post-fix gate detail: `reports/m31_mock_exam/m31_mock_exam_2026-03-08.json`

---

## 1) Patch Summary (Runtime Impact)

Key upgraded areas are present and active:
- Feature/regime engine: `libs/runtime/feature_engine.py`, `libs/runtime/regime.py`
- Strategy v1 stack: `libs/strategies/contracts.py`, `libs/strategies/v1/*`
- Universe/scanner: `libs/strategies/universe_builder.py`, `graphs/nodes/scanner_node.py`, `graphs/nodes/strategist_node.py`
- Data quality propagation: `libs/market/global_sentiment.py`, `libs/news/news_pipeline.py`, `graphs/nodes/build_decision_context.py`
- Decision explainability/sizing/exit: `graphs/nodes/decide_trade.py`, `libs/runtime/position_sizing.py`, `libs/runtime/exit_policy.py`
- Operator visibility: `libs/reporting/operator_visibility.py`, `scripts/run_operator_daily_summary.py`, `scripts/run_decision_story_report.py`, `scripts/run_run_card_report.py`
- M31 readiness checks: `scripts/run_m31_slo_incident_review_check.py`, `scripts/run_m31_mock_investor_exam_check.py`, `scripts/run_m31_mock_exam_readiness_check.py`

Operational impact:
- Decision context is richer and status-aware.
- Strategy packet has stronger explainability fields (`why`, `invalidation`, `sizing_inputs`).
- Operator reports are human-readable and health-classified.

---

## 2) Strategy V1 Baseline

Active baseline (documented):
- Strategy: `regime_momentum_v1`
- Manifest: `config/strategy_v1_exam_baseline.json`
- Baseline doc: `docs/plan/m31_15_strategy_v1_exam_baseline.md`

Determinism:
- Strategy logic itself is deterministic.
- Reproducibility is **partial** operationally because manifest is documented but not auto-bound at runtime load path.

Key reproducibility risk:
- No direct runtime loader reference to `config/strategy_v1_exam_baseline.json`.

---

## 3) Remaining Placeholder/Temporary Logic

Still present (intentional safety scaffolds):
- Rule strategist fallback: `libs/ai/strategist.py`, `libs/ai/strategist_factory.py`
- Scanner deterministic placeholder score branch: `graphs/nodes/scanner_node.py`
- Legacy static fallback universe path: `graphs/nodes/scan_candidates.py`
- Universe emergency fallback symbols: `libs/strategies/universe_builder.py`
- Partial news provider/scorer scaffolds: `libs/news/providers/google_news.py`, `libs/news/scorers/llm.py`, `libs/news/news_analyzer.py`

Conclusion:
- Acceptable for mock-safe resilience.
- Must be tightened before real-money mode.

---

## 4) Data Quality Propagation Check

Trace confirmed:
1. source normalization (`make_signal`) in `libs/data_quality/signal_contract.py`
2. global/news signal construction in `libs/market/global_sentiment.py`, `libs/news/news_pipeline.py`
3. context hydration in `graphs/nodes/build_decision_context.py`
4. strategist input bridging in `graphs/nodes/decide_trade.py`
5. visibility in `strategist_llm` events (`data/logs/events.jsonl`)

Result:
- `ok|fallback|unavailable` statuses are preserved through decision context and logs.
- Data failure is visible (not silently neutralized).

---

## 5) Operator Visibility Review

Reports inspected:
- `reports/operator_summary/operator_summary_2026-03-07.md`
- `reports/decision_story/decision_story_2026-03-07.md`
- `reports/run_cards/run_cards_2026-03-07.md`

Assessment:
- Daily summary: operator-friendly, health and actions visible at top.
- Story/cards: improved, but still noisy from non-trading/system runs (`UNKNOWN`/`unspecified` heavy).

Priority UX gap:
- Filter or separate non-trading run_ids from operator-facing story/card default view.

---

## 6) Safety Guarantee Validation

Classification:
- approval / guard precedence: **safe**
- mock vs real isolation: **needs_review** (mode interaction requires disciplined env profile)
- event schema compatibility: **safe**
- DTO/IO compatibility: **needs_review** (mostly additive; verify downstream consumers)
- idempotency assumptions: **safe**

Core references:
- `libs/approval/service.py`
- `libs/supervisor/intent_state_store.py`
- `graphs/nodes/execute_from_packet.py`
- `scripts/run_m24_guard_precedence_check.py`

---

## 7) M31 Mock Exam Readiness

Prerequisite status:
- M30 signoff artifact: pass
- M30 post-golive policy artifact: pass
- M31-1 SLO incident workflow: pass
- M31-2 mock investor exam gate: fail
- runtime profile correctness: partial (manual approval mismatch)
- guardrail freeze: pass

Readiness output:
- **NOT_READY** (current snapshot)

Blocking evidence:
- `approval_mode_manual` failed (`APPROVAL_MODE=auto`)
- `m31_mock_exam_gate_ok` failed (`rc=3`)

---

## 8) Top 5 Items Before Exam Start

1. Force manual approval mode (`APPROVAL_MODE=manual`)
2. Freeze strategy runtime path (`USE_STRATEGY_V1=true`, fixed `STRATEGY_V1_NAME`)
3. Close manifest-runtime binding gap (baseline manifest is doc-only today)
4. Reduce operator report noise from non-trading runs
5. Define sentiment-source health threshold for exam day acceptance

---

## 9) M32 Baseline Metrics (Measure Before M32 Work)

Required baseline set:
- p95 runtime latency
- strategist latency p95
- cost per run
- cost per intent
- API 429 rate
- guard block rate
- NOOP vs executed ratio

Primary measurement source:
- `scripts/generate_metrics_report.py`
- output: `reports/metrics/metrics_<day>.json`

---

## 10) Immediate Next Steps (Execution Order)

1. Switch exam profile to manual approval and rerun readiness gate.
2. Re-run mock exam gate (`m31_mock_investor_exam_check`) and confirm all required checks pass.
3. Lock strategy v1 runtime profile for exam window.
4. Generate operator reports for the exam day and review unknown/unspecified ratio.
5. Generate and freeze pre-M32 baseline metrics artifact.

---

## Appendix: Current Runtime Snapshot (Observed)

From `.env` snapshot during audit:
- `RUNTIME_PROFILE=staging`
- `KIWOOM_MODE=mock`
- `EXECUTION_MODE=real`
- `EXECUTION_ENABLED=true`
- `ALLOW_REAL_EXECUTION=false`
- `APPROVAL_MODE=auto`  <- blocker for M31 exam contract
- `SYMBOL_ALLOWLIST=005930,000660` (example from observed day; optional operational guard)
- `MAX_ORDER_NOTIONAL=1000000`
- `RISK_DAILY_LOSS_LIMIT=0.02`


