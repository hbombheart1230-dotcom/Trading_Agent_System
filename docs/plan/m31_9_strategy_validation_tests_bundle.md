# M31-9 Strategy Validation Test Bundle

- Date: 2026-03-07
- Goal: strengthen validation beyond platform safety toward deterministic strategy quality.

## Added test coverage

1. Data-quality failure-state contract
   - `tests/test_strategy_data_quality_signal_contract.py`
2. Decision explainability contract (`why` + `invalidation`)
   - `tests/test_decision_packet_explainability_contract.py`
3. Strategy v1 behavior (entry/exit/noop)
   - `tests/test_strategy_v1_regime_momentum.py`
4. Universe construction and scanner provenance
   - `tests/test_strategy_universe_builder.py`
   - `tests/test_scanner_universe_candidate_metadata.py`
5. Feature/regime extension regression
   - `tests/test_strategy_feature_engine_upgrade.py`
6. Sizing/exit scenario validation
   - `tests/test_strategy_sizing_exit_upgrade.py`

## Regression bundle (quick run)

```powershell
.\venv\Scripts\python.exe -m pytest -q `
  tests/test_m20_2_decide_trade_llm_flow.py `
  tests/test_m20_3_llm_event_logging.py `
  tests/test_m20_4_llm_ops_scripts.py `
  tests/test_strategy_data_quality_signal_contract.py `
  tests/test_decision_packet_explainability_contract.py `
  tests/test_strategy_v1_regime_momentum.py `
  tests/test_strategy_universe_builder.py `
  tests/test_scanner_universe_candidate_metadata.py `
  tests/test_strategy_feature_engine_upgrade.py `
  tests/test_strategy_sizing_exit_upgrade.py `
  tests/test_m29_1_feature_engine.py `
  tests/test_m29_2_scanner_feature_integration.py `
  tests/test_m29_3_monitor_exit_policy.py `
  tests/test_m29_4_monitor_position_sizing.py `
  tests/test_m22_skill_native_scanner_monitor.py `
  tests/test_m17_candidates_to_selected.py
```

Observed at implementation time: `58 passed`.
