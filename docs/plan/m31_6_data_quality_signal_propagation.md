# M31-6 Data-Quality Signal Propagation

- Date: 2026-03-07
- Goal: propagate `ok|fallback|unavailable` signal state through strategist input and observability.

## Scope

1. `graphs/nodes/decide_trade.py`
   - consumes canonical signal contracts:
     - `state["news_sentiment_signal"][symbol]`
     - `state["global_sentiment_signal"]`
   - keeps backward compatibility with legacy score-only fields.
   - propagates signal status/source/reason into:
     - `llm_context.news.*`
     - `risk_context.llm_context.*`
     - `strategist_llm` event payload

2. `scripts/query_strategist_llm_events.py`
   - displays sentiment status fields in human output:
     - `context_symbol_sentiment_status`
     - `context_global_sentiment_status`

## Compatibility

- Existing numeric fields remain unchanged:
  - `symbol_sentiment_score`
  - `global_sentiment_score`
- New fields are additive and optional for downstream consumers.

## Tests

- `tests/test_m20_2_decide_trade_llm_flow.py`
  - verifies signal status propagation into LLM input context.
- `tests/test_m20_3_llm_event_logging.py`
  - verifies strategist event payload includes status/source fields.
