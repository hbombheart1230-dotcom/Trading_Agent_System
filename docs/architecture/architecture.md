# Architecture

## Agents
- **Supervisor**: policy/risk + *approval gate*
- **Strategist**: decide themes/sectors and output candidate symbols (Top-N)
- **Scanner**: evaluate strategist candidates only and rank to Top-1
- **Monitor**: entry/exit monitoring only; emit **OrderIntent** (no execution)
- **Reporter**: replay logs and produce post-mortems

## Order flow (2-phase commit)
1) News/global sentiment context is attached to strategist input.
2) Strategist outputs `themes[]` + `candidates[]`.
3) Scanner scores strategist candidates and selects `top_stock`.
4) Monitor decides entry/exit for selected stock and creates `OrderIntent`.
5) Supervisor returns `approve/reject/modify`.
6) Only on approve, Execution skill places/cancels orders.

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
