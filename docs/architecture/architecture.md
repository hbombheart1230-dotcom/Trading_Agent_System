# Architecture

## Agents
- **Supervisor**: policy/risk + *approval gate*
- **Strategist**: decide *what to look at* and propose candidates/scenarios
- **Scanner**: execute data collection + feature extraction + ranking
- **Monitor**: watch signals and produce **OrderIntent** (no execution)
- **Reporter**: replay logs and produce post-mortems

## Order flow (2-phase commit)
1) Monitor creates `OrderIntent`
2) Supervisor returns `approve/reject/modify`
3) Only on approve, Execution skill places/cancels orders

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

