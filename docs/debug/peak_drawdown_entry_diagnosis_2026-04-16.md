# Peak Drawdown Entry/Exit Diagnosis (2026-04-16)

## Key Findings
- peak_drawdown trigger trades: **18** (all 18 closed lifecycles)
- peak_drawdown_exit_pct: **0.4637%** (same value across all peak-drawdown exits)
- observed peak_drawdown range: **-1.7629% ~ -0.8639%**
- average return_pct (peak_drawdown exits): **-0.0515%**
- min-hold/confirm safeguards are bypassed for peak_drawdown because it is treated as a hard-exit reason

## Entry Reason Top
- 13x `breakout_above_recent_high_with_vwap_structure_confirmation`
- 3x `breakout_above_recent_high_with_vwap_hold_and_volume_confirmation`
- 1x `pullback_rebound_above_vwap_with_volume_confirmation`
- 1x `pullback_structure_above_vwap_with_volume_confirmation`

## Decision Chain Top
- 10x `confirmed_exit_signal -> peak_drawdown -> breakout_above_recent_high_with_vwap_structure_confirmation -> peak_drawdown`
- 3x `confirmed_exit_signal -> peak_drawdown -> breakout_not_ready -> peak_drawdown`
- 2x `confirmed_exit_signal -> peak_drawdown -> breakout_above_recent_high_with_vwap_hold_and_volume_confirmation -> peak_drawdown`
- 1x `confirmed_exit_signal -> peak_drawdown -> pullback_rebound_above_vwap_with_volume_confirmation -> peak_drawdown`
- 1x `confirmed_exit_signal -> peak_drawdown -> volume_insufficient -> peak_drawdown`

## Trade Rows
| trade_id | symbol | entry_reason | hold_sec | hold_sec(ts) | peak_dd% | peak_dd_th% | stop_loss% | effective_stop% | return% |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| TRD_20260416_000660_01 | 000660 | pullback_rebound_above_vwap_with_volume_confirmation | 60 | 62 | -1.7629 | 0.4637 | 6.2695 | 3.0000 | 0.0000 |
| TRD_20260416_000660_02 | 000660 | breakout_above_recent_high_with_vwap_hold_and_volume_confirmation | 60 | 63 | -1.0739 | 0.4637 | 5.7679 | 3.0000 | 0.0000 |
| TRD_20260416_000660_03 | 000660 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 64 | -1.0699 | 0.4637 | 5.1020 | 3.0000 | 0.0000 |
| TRD_20260416_000660_04 | 000660 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 63 | -0.9000 | 0.4637 | 6.8237 | 3.0000 | 0.0000 |
| TRD_20260416_000660_05 | 000660 | breakout_above_recent_high_with_vwap_structure_confirmation | 563 | 566 | -1.1600 | 0.4637 | 6.0790 | 3.0000 | -0.2588 |
| TRD_20260416_000660_06 | 000660 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 63 | -0.9000 | 0.4637 | 6.8237 | 3.0000 | 0.0000 |
| TRD_20260416_000660_10 | 000660 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 132 | -0.8965 | 0.4637 | 6.9535 | 3.0000 | 0.0000 |
| TRD_20260416_000660_11 | 000660 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 62 | -0.9900 | 0.4637 | 6.9535 | 3.0000 | -0.0871 |
| TRD_20260416_000660_12 | 000660 | breakout_above_recent_high_with_vwap_hold_and_volume_confirmation | 60 | 62 | -0.9000 | 0.4637 | 6.9475 | 3.0000 | 0.0000 |
| TRD_20260416_000660_13 | 000660 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 63 | -1.0700 | 0.4637 | 4.4154 | 3.0000 | -0.1732 |
| TRD_20260416_000660_14 | 000660 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 63 | -0.9030 | 0.4637 | 6.9264 | 3.0000 | 0.0000 |
| TRD_20260416_000660_15 | 000660 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 63 | -0.8960 | 0.4637 | 6.9174 | 3.0000 | 0.0000 |
| TRD_20260416_005930_01 | 005930 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 63 | -1.0100 | 0.4637 | 8.0000 | 3.0000 | -0.1183 |
| TRD_20260416_005930_02 | 005930 | breakout_above_recent_high_with_vwap_structure_confirmation | 20 | 24 | -0.8946 | 0.4637 | 6.0218 | 3.0000 | 0.0000 |
| TRD_20260416_005930_03 | 005930 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 64 | -1.0100 | 0.4637 | 6.0790 | 3.0000 | -0.1153 |
| TRD_20260416_005930_04 | 005930 | breakout_above_recent_high_with_vwap_structure_confirmation | 60 | 63 | -0.8900 | 0.4637 | 6.1476 | 3.0000 | 0.0000 |
| TRD_20260416_047040_01 | 047040 | pullback_structure_above_vwap_with_volume_confirmation | 60 | 64 | -0.8639 | 0.4637 | 8.0000 | 3.0000 | 0.0000 |
| TRD_20260416_047040_04 | 047040 | breakout_above_recent_high_with_vwap_hold_and_volume_confirmation | 60 | 134 | -1.0700 | 0.4637 | 5.4873 | 3.0000 | -0.1742 |

## Code-level Cause (No Runtime Tuning Applied Yet)
- `libs/runtime/exit_policy.py:600-604` triggers immediate exit when `peak_drawdown <= -peak_drawdown_exit_pct`.
- `graphs/nodes/monitor_node.py:1330-1344` classifies `peak_drawdown` as hard-exit.
- `graphs/nodes/monitor_node.py:2990-3009` applies min-hold/confirm guards only when the reason is not hard-exit.
- `graphs/nodes/monitor_node.py:1189-1301` dynamically widens stop_loss/take_profit, but does not co-scale peak_drawdown_exit_pct, so peak-drawdown can dominate exits.