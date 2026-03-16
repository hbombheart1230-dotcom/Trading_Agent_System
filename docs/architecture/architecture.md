# Architecture

## Agents
- **Supervisor**: policy/risk + *approval gate*
- **Strategist**: decide themes/sectors and output optional candidate hints (Top-N)
- **Scanner**: retrieve Kiwoom candidates, hydrate candidate features/quote metrics, apply strategist frame (`themes`, `avoid_themes`, `playbook`, bias/priority), score/rank with breakdown, and select Top-1
- **Monitor**: entry/exit monitoring only; emit **OrderIntent** (no execution)
  - normal SELL stabilization: `MIN_HOLD_SECONDS`, `SELL_COOLDOWN`/`SELL_COOLDOWN_SEC`, `MONITOR_EXIT_CONFIRM_TICKS`
  - emergency exits (`emergency_halt`, `news_shock`) stay explicit and separate from normal exit confirmation
- **Reporter**: replay logs and produce post-mortems (deterministic baseline + optional passive AI review layer)
  - persists compact strategy-memory records for future Strategist advisory context
  - feeds operator UI and same-day operator summaries without changing live runtime behavior

## Canonical Implementation Entry Points
- **Commander/orchestration**: `graphs/commander_runtime.py`
  - wrapper: `graphs/nodes/commander_node.py`
  - legacy adapter: `libs/agent/commander.py`
  - phase-aware runtime: `preopen`, `session`, `closeout`
- **Strategist**: `graphs/nodes/strategist_node.py`
  - compatibility adapter: `libs/agent/strategist.py`
- **Scanner**: `graphs/nodes/scanner_node.py`
  - compatibility helper: `graphs/nodes/scan_candidates.py`
- **Monitor**: `graphs/nodes/monitor_node.py`
  - legacy interface: `libs/agent/monitor.py`

## Order flow (2-phase commit)
1) News/global sentiment context is attached to strategist input.
2) Strategist outputs strategic frame (`regime/sentiment/themes/playbook/bias/risk/monitor/report`) + optional `candidates[]` hints.
   - includes additive `scanner_source_policy` so Scanner can change which Kiwoom candidate sources are active for the run.
   - includes additive `macro_stress_overlay` so macro fear/pressure is explicit in downstream reasoning.
   - Canonical runtime key: `state["strategist_output"]` (DTO contract: `libs/strategies/contracts.py::StrategistOutput`).
   - Strategist also reads additive advisory memory from `state["recent_strategy_feedback"]`.
3) Scanner builds candidate pool from Kiwoom market data (condition/rank/theme/watchlist sources).
4) Scanner hydrates candidate-level features/quote metrics, reduces pool (halt/abnormal/illiquid guards), applies theme guidance, scores candidates, and selects `top_stock`.
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
- Additive reason ledger events are emitted with `stage=decision_trace` for post-run analysis.

- API selection follows a two-step process: discovery (Top-K) → decision.
