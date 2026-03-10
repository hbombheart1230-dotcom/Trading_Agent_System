# Architecture

## Agents
- **Supervisor**: policy/risk + *approval gate*
- **Strategist**: decide themes/sectors and output optional candidate hints (Top-N)
- **Scanner**: retrieve Kiwoom candidates, reduce candidate pool, score/rank with breakdown, and select Top-1
- **Monitor**: entry/exit monitoring only; emit **OrderIntent** (no execution)
  - normal SELL stabilization: `MIN_HOLD_SECONDS`, `SELL_COOLDOWN`/`SELL_COOLDOWN_SEC`, `MONITOR_EXIT_CONFIRM_TICKS`
  - emergency exits (`emergency_halt`, `news_shock`) stay explicit and separate from normal exit confirmation
- **Reporter**: replay logs and produce post-mortems

## Order flow (2-phase commit)
1) News/global sentiment context is attached to strategist input.
2) Strategist outputs `themes[]` (+ optional `candidates[]` hints).
3) Scanner builds candidate pool from Kiwoom market data (condition/rank/theme/watchlist sources).
4) Scanner reduces pool (halt/abnormal/illiquid guards), applies theme guidance, scores candidates, and selects `top_stock`.
5) Monitor decides entry/exit for selected stock and creates `OrderIntent`.
6) Supervisor returns `approve/reject/modify`.
7) Only on approve, Execution skill places/cancels orders.

## Observability (Event Logging)

- All runs share a `run_id` (generated at run start) and are traceable end-to-end.
- Nodes may emit **append-only** JSONL events to: `data/logs/events.jsonl`

### Event format (concept)
- `run_id`: string
- `stage`: node name (e.g., `ensure_token`)
- `event`: `start|end|error`
- `payload`: dict (small, safe to log)

### Rule
- Logging must be **observational only** (must not alter control flow).
- `start` and `end` are recommended for every node.

- API selection follows a two-step process: discovery (Top-K) → decision.
