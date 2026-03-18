# Trade Explain Report (2026-03-18)

- event_log_path: `data\logs\events.jsonl`
- executions_total: **12**
- sell_pairs_total: **6**

## Executive Summary

- symbols_executed: `['000660', '005930', '322000']`
- action_counts: `{'SELL': 6, 'BUY': 6}`
- symbol_side_counts: `{'322000:SELL': 1, '000660:BUY': 5, '000660:SELL': 4, '005930:BUY': 1, '005930:SELL': 1}`
- short_holds_lt_120s: **1**

## Agent Activity Snapshot

- `commander_router`: 935
- `monitor`: 288
- `decision_trace`: 836
- `execute_from_packet`: 693
- `strategist_llm`: 26
- `strategist`: 25
- `skill_execute`: 12
- `skill_result`: 12
- `skill_hydration`: 2
- `scanner`: 69
- `decision`: 2

## Report Inventory

- none

## Execution Timeline (Latest)

| ts | run_id | symbol | action | qty | price | strategy | reason |
| --- | --- | --- | --- | ---: | ---: | --- | --- |
| 2026-03-18T00:20:38+00:00 | `557b9830e01b47b8ba5a254085d50856` | 322000 | SELL | 1 | 0.0 | - | - |
| 2026-03-18T00:36:52+00:00 | `3b21ecfa0a4d43c391796daf635e275b` | 000660 | BUY | 1 | 0.0 | - | - |
| 2026-03-18T01:07:59+00:00 | `b07d1f5552714d34a666c9c49c19cba9` | 000660 | SELL | 1 | 0.0 | - | - |
| 2026-03-18T01:24:15+00:00 | `2ed16466800d4da0ac9849a7e509328a` | 000660 | BUY | 1 | 0.0 | - | - |
| 2026-03-18T01:38:07+00:00 | `a5582768e95746c9b1b6d9cb689f7fbc` | 000660 | SELL | 1 | 0.0 | - | - |
| 2026-03-18T01:54:43+00:00 | `78b1ebd804054abc8dc6c25c9a522b12` | 000660 | BUY | 1 | 0.0 | - | - |
| 2026-03-18T02:20:32+00:00 | `e3b0b286f100456a8406174a6330e788` | 000660 | SELL | 1 | 0.0 | - | - |
| 2026-03-18T02:36:20+00:00 | `c3649dba2e644353b445e7a1396b0329` | 000660 | BUY | 1 | 0.0 | - | - |
| 2026-03-18T03:13:31+00:00 | `91be9a2735a247aaacc669da0c8004b8` | 000660 | SELL | 1 | 0.0 | - | - |
| 2026-03-18T03:30:23+00:00 | `5b8241c60c1f4d608dfe65d658aca9b3` | 005930 | BUY | 1 | 0.0 | - | - |
| 2026-03-18T03:55:07+00:00 | `ec2c700d34564245903c51ccf6d606d8` | 005930 | SELL | 1 | 0.0 | - | - |
| 2026-03-18T04:11:03+00:00 | `bd1c8b9cf8924e5d91fa118dd361f9e6` | 000660 | BUY | 1 | 0.0 | - | - |

## Sell Pair Analysis (FIFO, Latest)

### SELL `557b9830e01b47b8ba5a254085d50856` / 322000
- sell_ts: 2026-03-18T00:20:38+00:00
- qty: sell=1, matched=0, unmatched=1
- hold_duration_sec_avg: **0** / estimated_realized_pnl: **0.0**
- entry_vs_exit_price: entry_avg=0.0, exit=0.0
- strategy: -
- sell_reason: -
- scanner_context: source=-, top_stock=-, top_score=None
- sentiment_context: symbol=None, global=None, status=(-, -)
- technical_context: signal_score=None, rsi14=None, ma20_gap=None, volatility20=None, composite=None
- monitor_context: exit_reason=hard_stop, monitor_reason=confirmed_exit_signal, price_source=position.current_price, feature_source=selected.features
- matched_buy_runs: `[]`

### SELL `b07d1f5552714d34a666c9c49c19cba9` / 000660
- sell_ts: 2026-03-18T01:07:59+00:00
- qty: sell=1, matched=1, unmatched=0
- hold_duration_sec_avg: **1867** / estimated_realized_pnl: **0.0**
- entry_vs_exit_price: entry_avg=0.0, exit=0.0
- strategy: -
- sell_reason: -
- scanner_context: source=-, top_stock=-, top_score=None
- sentiment_context: symbol=None, global=None, status=(-, -)
- technical_context: signal_score=None, rsi14=None, ma20_gap=None, volatility20=None, composite=None
- monitor_context: exit_reason=peak_drawdown, monitor_reason=confirmed_exit_signal, price_source=position.current_price, feature_source=selected.features
- matched_buy_runs: `['3b21ecfa0a4d43c391796daf635e275b']`

### SELL `a5582768e95746c9b1b6d9cb689f7fbc` / 000660
- sell_ts: 2026-03-18T01:38:07+00:00
- qty: sell=1, matched=1, unmatched=0
- hold_duration_sec_avg: **832** / estimated_realized_pnl: **0.0**
- entry_vs_exit_price: entry_avg=0.0, exit=0.0
- strategy: -
- sell_reason: -
- scanner_context: source=-, top_stock=-, top_score=None
- sentiment_context: symbol=None, global=None, status=(-, -)
- technical_context: signal_score=None, rsi14=None, ma20_gap=None, volatility20=None, composite=None
- monitor_context: exit_reason=peak_drawdown, monitor_reason=confirmed_exit_signal, price_source=position.current_price, feature_source=selected.features
- matched_buy_runs: `['2ed16466800d4da0ac9849a7e509328a']`

### SELL `e3b0b286f100456a8406174a6330e788` / 000660
- sell_ts: 2026-03-18T02:20:32+00:00
- qty: sell=1, matched=1, unmatched=0
- hold_duration_sec_avg: **1549** / estimated_realized_pnl: **0.0**
- entry_vs_exit_price: entry_avg=0.0, exit=0.0
- strategy: -
- sell_reason: -
- scanner_context: source=-, top_stock=-, top_score=None
- sentiment_context: symbol=None, global=None, status=(-, -)
- technical_context: signal_score=None, rsi14=None, ma20_gap=None, volatility20=None, composite=None
- monitor_context: exit_reason=take_profit, monitor_reason=confirmed_exit_signal, price_source=position.current_price, feature_source=selected.features
- matched_buy_runs: `['78b1ebd804054abc8dc6c25c9a522b12']`

### SELL `91be9a2735a247aaacc669da0c8004b8` / 000660
- sell_ts: 2026-03-18T03:13:31+00:00
- qty: sell=1, matched=1, unmatched=0
- hold_duration_sec_avg: **2231** / estimated_realized_pnl: **0.0**
- entry_vs_exit_price: entry_avg=0.0, exit=0.0
- strategy: -
- sell_reason: -
- scanner_context: source=-, top_stock=-, top_score=None
- sentiment_context: symbol=None, global=None, status=(-, -)
- technical_context: signal_score=None, rsi14=None, ma20_gap=None, volatility20=None, composite=None
- monitor_context: exit_reason=take_profit, monitor_reason=confirmed_exit_signal, price_source=position.current_price, feature_source=selected.features
- matched_buy_runs: `['c3649dba2e644353b445e7a1396b0329']`

### SELL `ec2c700d34564245903c51ccf6d606d8` / 005930
- sell_ts: 2026-03-18T03:55:07+00:00
- qty: sell=1, matched=1, unmatched=0
- hold_duration_sec_avg: **1484** / estimated_realized_pnl: **0.0**
- entry_vs_exit_price: entry_avg=0.0, exit=0.0
- strategy: -
- sell_reason: -
- scanner_context: source=-, top_stock=-, top_score=None
- sentiment_context: symbol=None, global=None, status=(-, -)
- technical_context: signal_score=None, rsi14=None, ma20_gap=None, volatility20=None, composite=None
- monitor_context: exit_reason=peak_drawdown, monitor_reason=confirmed_exit_signal, price_source=position.current_price, feature_source=selected.features
- matched_buy_runs: `['5b8241c60c1f4d608dfe65d658aca9b3']`

## Data Gaps

- scanner_score_breakdown_missing_total: 6
- news_items_missing_total: 12
- note: news headline text and scanner score_breakdown are limited by current event-log payload policy.
