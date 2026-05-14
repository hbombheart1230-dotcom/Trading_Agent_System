# Daily Patch Log - 일일 패치 노트

## Folder Title Recommendation

Recommended title: `Daily Patch Log - 일일 패치 노트`

This folder is the operator-facing daily record for runtime, strategy, reporting, and safety patches.

## Naming Rule

Use one file per trading day:

```text
YYYY-MM-DD_short-main-title.md
```

Examples:

- `2026-04-29_strategy-conservatism-runtime-guards.md`
- `2026-04-30_entry-gate-reporting-memory-defaults.md`
- `2026-05-04_intraday-cash-truth-ai-report-check.md`

## What To Record

- reason for the patch
- changed runtime behavior
- changed report/operator visibility
- validation commands and results
- restart status, when the live process was restarted
- remaining follow-up items

Keep this folder concise. Detailed design notes can stay in each owner folder, and this folder should link or summarize the daily operational change.

## Latest Weekend Review

- `2026-05-09_weekend-validation-report-regeneration-review.md`: 2026-04-29 through 2026-05-08 patch status review, report regeneration timeout fix, and next live-check list.

## Latest Live Hotfix

- `2026-05-12_live-monitor-crash-hotfix.md`: live monitor `NameError` hotfix, strategy horizon translation verification, scanner/monitor chart-context runtime check, and restart status.
- `2026-05-12_pending-exit-sell-guard.md`: 000660 pending exit confirmation mismatch fix, decision/executor SELL hard guard, and report wording alignment.
- `2026-05-12_candidate-cascade-expansion-hotfix.md`: restored Commander-expanded runner-up evaluation when a stale strategist `cascade_enabled=false` conflicted with `max_priority_rank=10` / `max_runner_ups=9`.
- `2026-05-12_vwap-exit-fresh-minute-source-hotfix.md`: fixed immediate VWAP exit risk by preferring fresh held-symbol minute VWAP over stale scanner feature `engine_vwap_distance`.
- `2026-05-12_recent-buy-fill-settle-sell-guard.md`: blocks structural SELL orders while a same-symbol recent BUY is only partially reflected, while preserving emergency/stop exits.
- `2026-05-12_full-close-trade-report-gate.md`: final trade reports are now written only after cumulative SELL quantity fully closes the entry quantity; partial exits remain lifecycle-only until full liquidation.
- `2026-05-12_cost-floor-and-truth-surface-hotfix.md`: prevents metric-only VWAP/low-break hard invalidation from bypassing cost-aware profit floors on small positive gross gains, and labels ambiguous `ka10077` report values as unconfirmed observations.
- `2026-05-12_scanner-monitor-chart-fit-verification.md`: verified 2026-05-11 scanner/monitor chart-fit wiring, restored Stage 2 chart-fit field visibility, and fixed common-stock `dstr_rt` being misread as ETF deviation.
- `2026-05-12_llm-report-folder-dedup-and-trade-summary-copy.md`: classified LLM run folders now win over flat date-root folders, duplicate flat artifacts merge into the classified folder, and strategist summaries are copied into the matching trade bundle.
- `2026-05-12_defensive-top3-and-repeat-loss-guard.md`: defensive/risk-off repeated blocker no-trade streaks can reopen conservative top3 cascade when capacity remains, and same-day repeat loser symbols receive a much stronger scanner prior penalty.
- `2026-05-12_human-chart-guard-chartfit-horizon-alignment.md`: added hard buy blocking for broken human-chart context, scanner chart-fit report visibility, and strategy horizon enum cleanup.
- `2026-05-12_monitor-human-chart-positive-entry-setup.md`: adds a conservative A-grade human-chart entry setup path so the monitor can promote near-ready clean VWAP/structure setups, not only block weak ones.
- `2026-05-12_scanner-macro-chartfit-monitor-quality.md`: separates scanner bigger-picture chart-fit from monitor live-entry chart-fit, adds scanner macro soft rank bias, and adds monitor candle/VWAP/reward-room setup quality fields.
- `2026-05-13_trade-summary-entry-exit-evidence-lines.md`: trade summaries now surface concrete entry evidence values and trend-breakdown exit basis lines.
- `2026-05-13_time-limit-cost-floor-reassessment.md`: changes `max_hold` / `time_stop` from hard SELL triggers into cost-aware time-limit reassessment, strengthens late-entry reward-room blocking, and marks `SELL + hold` as a mismatch.
- `2026-05-13_peak-profit-protection-report-evidence.md`: fixes gross-vs-effective profit-floor alignment, urgent peak-drawdown confirmation, per-position strategy pinning, and monitor evidence coverage in trade reports.
- `2026-05-13_operator-summary-pattern-performance.md`: adds observation-only strategist/scanner/monitor pattern performance aggregation to daily, weekly, monthly, and symbol operator summaries.
- `2026-05-13_strategist-summary-stage-meta-rendering-fix.md`: fixes strategist summary markdown rendering by loading sidecar LLM metadata, inferring Stage 2/3/4 calls, and regenerating the affected 2026-05-13 run/trade summaries.
- `2026-05-14_vwap-reclaim-strategy-and-human-chart-entry-relaxation.md`: replaces new `leader_vwap_reclaim_pullback` output with `vwap_reclaim_pullback`, adds pullback evidence subtypes and weak fallback gating, and relaxes A-grade human-chart near-ready BUY promotion.
