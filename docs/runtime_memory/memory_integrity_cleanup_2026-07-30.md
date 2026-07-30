# Runtime Memory Integrity Cleanup

Date: 2026-07-30

## Conclusion

Runtime memory was not globally disabled. The system had three different states mixed
together:

1. canonical performance memory was loaded from `reports/performance/*`
2. legacy Reporter feedback was also loaded from `data/strategy_memory/*`
3. `memory_usage_trace.used=true` meant that a packet was visible in context, not
   necessarily that a deterministic scanner or monitor delta was applied

The main defect was the legacy Reporter adapter. Run-level realized PnL in KRW was
divided by playbook/theme appearance counts and exposed as `avg_return`. This produced
impossible values such as 16,259 or 16,763 in July Strategist inputs.

## Authority Contract

Performance authority:

- daily: `reports/performance/<YYYY-MM-DD>/strategy_memory.json`
- weekly/monthly: Commander memory packets rolled up from canonical performance memory
- symbol: `reports/symbols/<SYMBOL>/symbol_memory.json`, subject to existing quality and
  recency gates

Legacy Reporter feedback:

- source: `data/strategy_memory/feedback.jsonl` and `data/strategy_memory/daily/*.json`
- role: qualitative Reporter frequency and issue context only
- must not publish win rate, return, expectancy, or directional performance attribution
- must not override canonical performance memory

## Freshness Contract

Legacy Reporter feedback is excluded from Strategist decision input when:

- no records exist
- the feature is disabled
- the latest record is more than 7 calendar days older than the Strategist as-of day

An excluded packet retains only audit metadata:

- status
- latest feedback day
- age
- performance authority
- quality flags

It does not retain playbook/theme performance, strengths, weaknesses, or Reporter
recommendations in the compact LLM input.

Observed real-data result:

- as-of day: 2026-07-21
- latest legacy feedback: 2026-06-18
- age: 33 days
- result: `status=stale`
- result: legacy playbook performance excluded

## Unit Contract

The following fields must never be treated as interchangeable:

- KRW realized PnL
- decimal return
- percentage return
- playbook/theme appearance count

Legacy Reporter records do not contain attributable playbook/theme returns. Their
aggregates therefore expose:

- `appearance_count`
- `report_count` or alignment frequency
- `performance_metric_usable=false`
- `metric_basis=qualitative_reporter_frequency_only`

They do not expose fabricated `avg_return` or `win_rate`.

## Application Trace Contract

`memory_usage_trace` now distinguishes:

- `used`: the layer was visible and selected as Strategist context
- `use_kind=context_only`: context was visible, with no deterministic delta
- `use_kind=context_and_deterministic_delta`: context was visible and daily memory
  produced scanner or monitor delta fields
- `use_kind=blocked`: visible but gated
- `deterministic_delta_applied`: a scanner or monitor delta exists

Top-level `application_summary` reports:

- context layer count
- scanner delta applied
- monitor delta applied
- any deterministic delta applied
- LLM memory usage status, when reported
- whether a causal strategy change was attributable

The trace no longer claims that the selected playbook was maintained because of memory
when no causal evidence exists. In that case it reports
`memory_context_visible_no_attributed_playbook_change`.

## Import Boundary

`libs.reporting` now resolves public exports lazily. Runtime memory modules may import
small reporting artifact helpers without initializing the full daily-report and
trade-report dependency graph. This removes test and runtime behavior that depended on
module import order.

## Behavior Impact

Unchanged:

- Commander memory priority
- canonical performance-memory calculations
- symbol-memory eligibility gates
- scanner memory delta calculations
- monitor memory delta calculations
- entry, exit, order, and execution rules

Corrected:

- invalid legacy performance numbers are no longer sent to Strategist
- stale legacy Reporter advice is no longer sent as current evidence
- memory trace no longer overstates deterministic or causal application

## Verification

Required regression surfaces:

- strategy feedback builder
- Strategist compact LLM input
- Commander memory policy
- daily/weekly/monthly/symbol memory packets
- scanner and monitor memory bias
- trade memory reporting surface
- Strategist explanation contract
- reporting package compatibility

Fresh live verification should confirm:

1. `recent_strategy_feedback.status` is `stale`, `empty`, or `ok` as expected
2. stale packets contain no `recent_playbook_performance`
3. canonical `strategy_memory` and `memory_packets` remain populated
4. `application_summary.deterministic_delta_applied` agrees with actual delta keys
5. no return-like value is sourced from legacy KRW PnL
