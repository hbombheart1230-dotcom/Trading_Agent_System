# Current Runtime Env Inventory

## Executive Summary

Current runtime env usage is a mixed-generation configuration surface: stable safety/exit/pipeline knobs, real but compatibility-oriented legacy gates, and scoring env names that no longer match the current `5-3` policy-aware monitor semantics.

The three cleanup axes with the highest leverage are:

1. Scoring / shadow env naming drift
2. Legacy allow-flags that now behave as compatibility escape hatches
3. Documentation gaps around commander routing, cache, and reporting cadence envs

Inventory comes before value changes because the current runtime already spans threshold/rule behavior, policy-aware monitor interpretation, reporting, and legacy fallback surfaces. Changing values before classifying the env surface would make it harder to tell whether behavior differences came from architecture, configuration, or both.

## Keep as-is

These envs are referenced, aligned with the current runtime architecture, and should remain first-class knobs.

- `MAX_ORDER_QTY`
- `MAX_ORDER_NOTIONAL`
- `RISK_DAILY_LOSS_LIMIT`
- `RISK_MAX_POSITIONS`
- `AI_STRATEGIST_PROVIDER`
- `AI_STRATEGIST_ENDPOINT`
- `AI_STRATEGIST_MODEL`
- `AI_STRATEGIST_TIMEOUT_SEC`
- `AI_STRATEGIST_MAX_TOKENS`
- `AI_STRATEGIST_RETRY_MAX`
- `AI_STRATEGIST_STRICT`
- `USE_EXIT_POLICY`
- `POST_EXIT_COOLDOWN_SEC`
- `EXIT_POLICY_USE_EOD_FLAT`
- `EXIT_POLICY_EOD_FLAT_CUTOFF_MIN`
- `MIN_HOLD_SECONDS`
- `MONITOR_EXIT_CONFIRM_TICKS`
- `MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION`
- `M13_TICK_PIPELINE`
- `CANDIDATE_SOURCE`
- `TOP_CANDIDATE_POOL`
- `KIWOOM_CANDIDATE_CONDITION_LIMIT`
- `KIWOOM_CANDIDATE_INCLUDE_CHANGE_RATE`
- `REPORTER_AI_REVIEW_ENABLED`
- `TRADE_REPORT_AI_ENABLED`

## Keep but document better

These envs are alive and useful, but their role is easy to misread without architecture context.

- `OPENROUTER_HTTP_REFERER`
- `OPENROUTER_X_TITLE`
- `REPORTER_AI_REVIEW_TEMPERATURE`
- `REPORTER_AI_REVIEW_MAX_TOKENS`
- `TRADE_REPORT_AI_GENERATE_ON_OPEN`
- `USE_STRATEGY_MEMORY_FEEDBACK`
- `STRATEGY_MEMORY_RECENT_RUNS`
- `KIWOOM_CANDIDATE_LIVE_FETCH`
- `BLOCK_STATIC_FALLBACK_WHEN_KIWOOM_EMPTY`
- `STRICT_KIWOOM_CANDIDATES_ONLY`
- `SELL_COOLDOWN_SEC`
- `COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED`
- `COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED`

## Legacy / deprecated candidate

These envs are still read in code, but they no longer fit the current preferred runtime path and should be treated as compatibility controls rather than first-class operational knobs.

- `ALLOW_LEGACY_RULE_RUNTIME`
- `ALLOW_LEGACY_STRATEGY_V1_RUNTIME`

## Rename candidate

These envs are still active, but the names now overstate or misdescribe their real role under `5-3`.

- `MONITOR_SCORING_ENABLED`
- `MONITOR_SCORING_SHADOW_MODE`
- `MONITOR_ENTRY_SCORE_THRESHOLD`

The core issue is that scoring is no longer an independent decision owner. It now behaves as evidence/scoring support inside Monitor, while final BUY/WAIT ownership remains with legacy gates plus narrow policy-aware integration.

## No immediate runtime action needed

No env value in this inventory requires immediate hotfix-style adjustment.

In particular:

- `AI_STRATEGIST_STRICT=true` is aligned with current architecture and should stay
- `COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED=false` is a real feature gate, not a dead switch
- scoring env values can remain as they are for now, even though naming cleanup is recommended later
- legacy allow-flags can remain `false` until an intentional cleanup/removal pass is scheduled

## Safety / Risk

| key | current_value_example | referenced_in_code | main_reference_locations | runtime_category | current_meaning | current_architecture_fit | recommendation | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `MAX_ORDER_QTY` | `10` | yes | `graphs/nodes/execute_from_packet.py`, `libs/agent/executor/executor_agent.py` | safety / execution guard | Maximum per-order quantity clamp | Strong fit | keep | Still used directly by execution-facing guard code |
| `MAX_ORDER_NOTIONAL` | `1000000` | yes | `graphs/nodes/execute_from_packet.py`, `libs/agent/executor/executor_agent.py` | safety / execution guard | Maximum notional cap per order | Strong fit | keep | Still enforced before execution packets are sent |
| `RISK_DAILY_LOSS_LIMIT` | `0.1` | yes | `libs/risk/supervisor.py`, `libs/core/settings.py` | safety / account risk | Daily loss guard threshold | Strong fit | keep | Still part of supervisor-level safety gating |
| `RISK_MAX_POSITIONS` | `1` | yes | `libs/risk/supervisor.py`, `libs/core/settings.py` | safety / position risk | Maximum simultaneous positions | Strong fit | keep | Active runtime risk control |

## LLM / Strategist Runtime

| key | current_value_example | referenced_in_code | main_reference_locations | runtime_category | current_meaning | current_architecture_fit | recommendation | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `AI_STRATEGIST_PROVIDER` | `openai` | yes | `graphs/nodes/strategist_node.py`, `libs/ai/strategist_config.py`, `libs/ai/strategist_factory.py` | strategist runtime | Selects strategist provider mode | Strong fit | keep | Still controls AI vs compatibility provider behavior |
| `AI_STRATEGIST_ENDPOINT` | `https://openrouter.ai/api/v1/chat/completions` | yes | `libs/ai/strategist_config.py`, `libs/ai/strategist_factory.py` | strategist runtime | Strategist provider endpoint | Strong fit | keep | Missing endpoint can block strategist when strict mode is active |
| `AI_STRATEGIST_MODEL` | `deepseek/deepseek-v3.2` | yes | `libs/ai/strategist_config.py` | strategist runtime | Strategist model selection | Strong fit | keep | First-class live runtime control |
| `AI_STRATEGIST_TIMEOUT_SEC` | `15` | yes | `libs/ai/strategist_config.py`, `libs/llm/openrouter_client.py` | strategist runtime | Strategist request timeout | Strong fit | keep | Also feeds OpenRouter timeout fallback path |
| `AI_STRATEGIST_MAX_TOKENS` | `8192` | yes | `libs/ai/strategist_config.py` | strategist runtime | Strategist max token budget | Strong fit | keep | Active provider configuration |
| `AI_STRATEGIST_RETRY_MAX` | `3` | yes | `libs/ai/providers/openai_provider.py` | strategist runtime | Strategist retry count | Strong fit | keep | Direct runtime resilience knob |
| `AI_STRATEGIST_STRICT` | `true` | yes | `libs/ai/strategist_factory.py`, `libs/ai/strategist_config.py` | strategist runtime / safety posture | Blocks legacy fallback when strategist LLM config/provider is unavailable | Strong fit | keep | This matches the current system philosophy: no silent fallthrough to older strategy runtime |
| `OPENROUTER_HTTP_REFERER` | GitHub URL | yes | `libs/llm/openrouter_client.py` | transport metadata | OpenRouter request metadata | Neutral fit | keep but document better | Operationally harmless, but not strategy logic |
| `OPENROUTER_X_TITLE` | `Trading_Agent_System` | yes | `libs/llm/openrouter_client.py` | transport metadata | OpenRouter request metadata title | Neutral fit | keep but document better | Metadata only, not architecture-defining |

## Reporting / Memory

| key | current_value_example | referenced_in_code | main_reference_locations | runtime_category | current_meaning | current_architecture_fit | recommendation | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `REPORTER_AI_REVIEW_ENABLED` | `true` | yes | `libs/reporting/reporter_ai_review.py` | reporting | Enables reporter AI review pass | Good fit | keep | Independent of trading decisions |
| `REPORTER_AI_REVIEW_TEMPERATURE` | `0.2` | yes | `libs/reporting/reporter_ai_review.py` | reporting | Reporter AI review generation control | Good fit | keep but document better | Meaning is clear, but role is post-trade/reporting only |
| `REPORTER_AI_REVIEW_MAX_TOKENS` | `8192` | yes | `libs/reporting/reporter_ai_review.py` | reporting | Reporter AI review token budget | Good fit | keep but document better | Same as above |
| `TRADE_REPORT_AI_ENABLED` | `true` | yes | `libs/reporting/trade_report_ai.py`, `scripts/run_live_execution_bundle_report.py` | reporting | Enables AI trade report generation | Good fit | keep | Live and artifact-relevant |
| `TRADE_REPORT_AI_GENERATE_ON_OPEN` | `true` | yes | `scripts/run_live_execution_bundle_report.py` | reporting cadence | Generates trade report on open path | Good fit | keep but document better | Controls generation timing, not trading behavior |
| `USE_STRATEGY_MEMORY_FEEDBACK` | `true` | yes | `graphs/nodes/strategist_node.py` | strategy memory | Enables strategy memory feedback enrichment | Good fit | keep but document better | Meaningful, but needs clearer docs about scope and effect |
| `STRATEGY_MEMORY_RECENT_RUNS` | `12` | yes | `graphs/nodes/strategist_node.py` | strategy memory | Recent run window for strategy memory | Good fit | keep but document better | Still live and architecture-aligned |

## Candidate / Data Source / Pipeline

| key | current_value_example | referenced_in_code | main_reference_locations | runtime_category | current_meaning | current_architecture_fit | recommendation | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `M13_TICK_PIPELINE` | `integrated_chain` | yes | `graphs/pipelines/m13_tick.py` | pipeline selection | Selects tick pipeline mode | Strong fit | keep | Core pipeline selector |
| `CANDIDATE_SOURCE` | `kiwoom` | yes | `graphs/nodes/scan_candidates.py`, `graphs/nodes/scanner_node.py`, `libs/agent/scanner.py` | candidate sourcing | Selects candidate provider path | Strong fit | keep | First-class scanner/runtime knob |
| `TOP_CANDIDATE_POOL` | `30` | yes | `graphs/nodes/scan_candidates.py`, `graphs/nodes/scanner_node.py` | candidate sizing | Top-N pool size before filtering | Strong fit | keep | Stable runtime parameter |
| `KIWOOM_CANDIDATE_CONDITION_LIMIT` | `200` | yes | `graphs/nodes/scan_candidates.py`, `graphs/nodes/scanner_node.py` | candidate sourcing | Kiwoom candidate size limit | Strong fit | keep | Active source shaping control |
| `KIWOOM_CANDIDATE_INCLUDE_CHANGE_RATE` | `true` | yes | `graphs/nodes/scan_candidates.py`, `graphs/nodes/scanner_node.py` | candidate sourcing | Adds change-rate field in candidate fetch | Strong fit | keep | Live data shaping control |
| `KIWOOM_CANDIDATE_LIVE_FETCH` | `true` | yes | `libs/strategies/candidates/kiwoom_candidate_provider.py` | candidate sourcing | Enables live Kiwoom fetch path | Good fit | keep but document better | Important but easy to confuse with source selection itself |
| `BLOCK_STATIC_FALLBACK_WHEN_KIWOOM_EMPTY` | `true` | yes | `graphs/nodes/scanner_node.py` | fallback control | Prevents static fallback when Kiwoom returns empty | Good fit | keep but document better | Architecture-significant fallback control |
| `STRICT_KIWOOM_CANDIDATES_ONLY` | `true` | yes | `graphs/nodes/scanner_node.py` | fallback control | Forces Kiwoom-only candidate behavior | Good fit | keep but document better | Useful, but deserves clearer operational docs |

## Exit / Execution Guard

| key | current_value_example | referenced_in_code | main_reference_locations | runtime_category | current_meaning | current_architecture_fit | recommendation | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `USE_EXIT_POLICY` | `true` | yes | `graphs/nodes/monitor_node.py`, `graphs/nodes/decide_trade.py`, `graphs/nodes/strategist_node.py` | exit policy | Enables exit policy path | Strong fit | keep | Still part of preferred runtime |
| `POST_EXIT_COOLDOWN_SEC` | `180` | yes | `graphs/nodes/monitor_node.py`, `graphs/nodes/decide_trade.py` | execution guard | Cooldown after exit | Strong fit | keep | Direct behavior control |
| `EXIT_POLICY_USE_EOD_FLAT` | `true` | yes | `graphs/nodes/monitor_node.py`, `graphs/nodes/decide_trade.py`, `graphs/nodes/strategist_node.py` | exit policy | Enables EOD flattening | Strong fit | keep | Aligned with current execution safety |
| `EXIT_POLICY_EOD_FLAT_CUTOFF_MIN` | `10` | yes | `graphs/nodes/monitor_node.py`, `graphs/nodes/decide_trade.py` | exit policy | Minutes before close for forced flattening | Strong fit | keep | Stable runtime behavior knob |
| `MIN_HOLD_SECONDS` | `600` | yes | `graphs/nodes/monitor_node.py`, `graphs/nodes/decide_trade.py`, `graphs/nodes/strategist_node.py` | holding guard | Minimum hold duration | Strong fit | keep | Still part of current guard stack |
| `SELL_COOLDOWN_SEC` | `300` | yes | `graphs/nodes/monitor_node.py`, `graphs/nodes/decide_trade.py`, `graphs/nodes/strategist_node.py` | execution guard | Sell cooldown duration | Good fit | keep but document better | `SELL_COOLDOWN` alias support still exists in parts of the codebase; docs should clarify preferred key |
| `MONITOR_EXIT_CONFIRM_TICKS` | `2` | yes | `graphs/nodes/monitor_node.py`, `graphs/nodes/strategist_node.py` | exit guard | Exit confirmation tick count | Strong fit | keep | Live monitor behavior control |
| `MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION` | `true` | yes | `graphs/nodes/monitor_node.py`, `graphs/commander_runtime.py` | entry guard | Prevents buy while open position exists | Strong fit | keep | Still aligned with current one-position behavior |

## Commander Runtime / Routing

| key | current_value_example | referenced_in_code | main_reference_locations | runtime_category | current_meaning | current_architecture_fit | recommendation | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `COMMANDER_MONITOR_ONLY_WHEN_HOLDING_ENABLED` | `true` | yes | `graphs/commander_runtime.py` | commander routing | Forces monitor-only route when holding | Good fit | keep but document better | Important routing behavior, but easy to miss without commander docs |
| `COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED` | `false` | yes | `graphs/commander_runtime.py` | commander routing / cache | Enables cached strategist reuse when flat | Good fit | keep but document better | Real feature gate, not dead; current `false` setting just keeps reuse disabled |

## Legacy Compatibility / Architecture Drift

| key | current_value_example | referenced_in_code | main_reference_locations | runtime_category | current_meaning | current_architecture_fit | recommendation | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `ALLOW_LEGACY_RULE_RUNTIME` | `false` | yes | `libs/ai/strategist_factory.py`, `graphs/nodes/decide_trade.py` | legacy compatibility | Allows older rule runtime path | Weak fit | deprecate candidate | Still read, but should be treated as compatibility escape hatch rather than normal operations knob |
| `ALLOW_LEGACY_STRATEGY_V1_RUNTIME` | `false` | yes | `libs/ai/strategist_factory.py`, `graphs/nodes/decide_trade.py` | legacy compatibility | Allows older strategist v1 path | Weak fit | deprecate candidate | Same pattern as above |

These flags are not dead switches, but they are no longer aligned with the preferred policy-aware runtime path. With `AI_STRATEGIST_STRICT=true`, they sit outside the intended operating posture.

## Scoring / Shadow / Policy Transition

| key | current_value_example | referenced_in_code | main_reference_locations | runtime_category | current_meaning | current_architecture_fit | recommendation | notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `MONITOR_SCORING_ENABLED` | `false` | yes | `libs/runtime/intraday_monitor_signals.py` | scoring / evidence | Enables scoring computation mode flag | Partial fit | rename candidate | Still read, but scoring no longer owns final decision |
| `MONITOR_SCORING_SHADOW_MODE` | `true` | yes | `libs/runtime/intraday_monitor_signals.py` | scoring / evidence | Controls shadow-style scoring behavior | Partial fit | rename candidate | Name is now misleading because scoring is evidence/support, not shadow decision ownership |
| `MONITOR_ENTRY_SCORE_THRESHOLD` | `3` | yes | `libs/runtime/intraday_monitor_signals.py` | scoring / evidence | Threshold for score-based evidence output | Partial fit | rename candidate | Still active in scoring/evidence calculation, but no longer a primary final decision threshold |

Current `5-3` interpretation:

- these envs are still live
- they still affect scoring/evidence outputs
- they no longer act as an independent decision owner
- the names now drift from their actual architectural role

## Special Diagnostics

### Legacy flags actual usage

`ALLOW_LEGACY_RULE_RUNTIME` and `ALLOW_LEGACY_STRATEGY_V1_RUNTIME` are still referenced in real code paths. They are not dead. However, they now function as compatibility gates for older runtimes, not as first-class controls in the preferred architecture.

Recommendation:

- keep them `false`
- mark them as deprecated candidates
- document them as escape hatches, not normal runtime tuning knobs

### Scoring envs vs current architecture

`MONITOR_SCORING_ENABLED`, `MONITOR_SCORING_SHADOW_MODE`, and `MONITOR_ENTRY_SCORE_THRESHOLD` are still loaded by `libs/runtime/intraday_monitor_signals.py`. They still influence score computation, score traces, and evidence-related output.

What changed under `5-3` is ownership:

- scoring is no longer the final decision owner
- legacy monitor gates still own final BUY/WAIT
- narrow `policy_aware_gating` can apply limited interpretation-aware adjustment

Because of that, the current env names now describe old architecture better than current behavior. This is why they are rename candidates rather than immediate removal candidates.

### `AI_STRATEGIST_STRICT` meaning

`AI_STRATEGIST_STRICT` still matters and matches the current runtime philosophy.

In practice it helps ensure:

- missing strategist LLM config does not silently fall back into older runtime modes
- unsupported provider selection blocks rather than silently downgrades
- AI strategist operation remains an explicit requirement when configured as such

This env should remain active and should not be treated as legacy drift.

### `COMMANDER_STRATEGIST_CACHE_WHEN_FLAT_ENABLED`

This env is still referenced in active commander routing code. It is not a dead switch.

Current status:

- referenced in cached strategist reuse preference logic
- referenced in flat-state strategist reuse gating
- currently set to `false`, which simply keeps the feature disabled

Recommendation:

- keep
- document more clearly
- do not remove based only on the current value

## Current Runtime Inventory Judgment

The current env surface is usable, but it is not yet conceptually tidy.

The most important architectural mismatch is not that envs are missing. It is that:

- producer-side policy is moving toward explicit interpretation policy
- Monitor is now policy-aware
- but parts of env naming still reflect older threshold-heavy or shadow-scoring ownership assumptions

That means the next cleanup should be semantic and documentation-driven first, not value-driven.

## Weekend Follow-up Recommendations

1. Freeze this inventory and use it as the reference sheet for current runtime config decisions
2. Clean up `.env.example` and runtime/config docs around legacy flags, cache controls, and reporting cadence knobs
3. Plan a rename/deprecation migration for scoring/shadow envs after confirming the producer-side explicit policy shape settles

## Recommended Follow-up Sequence

1. Finalize inventory and category decisions
2. Update `.env.example` and config documentation to match the inventory
3. Execute targeted deprecated/rename migration for legacy flags and scoring envs
