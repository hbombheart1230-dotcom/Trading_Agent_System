# M31-14 Data Quality Signal State Propagation

- Date: 2026-03-07
- Goal: separate neutral score vs unavailable/fallback state and propagate signal quality through strategist/scanner without breaking existing score contracts.

## What Changed

1. Robust signal timestamp parsing
- File: `libs/data_quality/signal_contract.py`
- `make_signal()` now accepts:
  - epoch int/float
  - ISO datetime string (`...Z`/offset)
  - fallback to current epoch when invalid

2. Strategist signal propagation
- File: `graphs/nodes/strategist_node.py`
- Global sentiment now emits both:
  - `state["global_sentiment"] = {"score": ...}` (legacy-compatible)
  - `state["global_sentiment_signal"] = {score,status,source,reason,ts}`
- News sentiment now emits both:
  - `state["news_sentiment"][symbol] = score` (legacy-compatible)
  - `state["news_sentiment_signal"][symbol] = {score,status,source,reason,ts}`
- Disabled paths are explicit:
  - global: `fallback/global_sentiment_disabled`
  - news: `fallback/news_analysis_disabled`

3. Scanner signal-aware consumption + explainability
- File: `graphs/nodes/scanner_node.py`
- Score priority upgraded:
  - global score: prefer `global_sentiment_signal.score`
  - news score: prefer `news_sentiment_signal[symbol].score`
- Legacy fallback compatibility retained:
  - `mock_*` / legacy score maps still supported
- Per-candidate component metadata now includes:
  - `news_sentiment_status/source/reason`
  - `global_sentiment_status/source/reason`

## Compatibility

- Existing float score contracts remain unchanged:
  - `state["global_sentiment"]["score"]`
  - `state["news_sentiment"][symbol]`
- Existing scanner scoring behavior is preserved unless signal maps are explicitly provided.

## Tests

- Added:
  - `tests/test_data_quality_state_propagation.py`
    - strategist emits explicit fallback signals when analysis disabled
    - scanner prefers signal score over legacy score
    - scanner includes signal status fields in components
- Regression:
  - full suite pass: `501 passed`
