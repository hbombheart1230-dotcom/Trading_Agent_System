# Symbol Read Model Alignment (2026-04-19)

## Goal

Clarify the relationship between:

- `libs/reporting/symbol_read_model.py`
- `reports/symbols/<SYMBOL>/symbol_memory.json`
- `libs/reporting/symbol_trade_report.py`

The objective is not to delete one immediately.
The objective is to stop overlap from growing while preserving current consumers.

## Current Runtime Reality

`symbol_read_model.py` is still actively used.

Current consumers:

1. `graphs/nodes/strategist_node.py`
- `_load_deterministic_read_models(...)`
- builds `symbol_patterns[...] = build_symbol_read_model(...)`

2. `libs/reporting/operator_visibility.py`
- `build_separated_operator_brief(...)`
- uses `build_symbol_read_model(...)` as fallback scope

3. tests
- `tests/test_symbol_read_model.py`

So `symbol_read_model.py` is not dead code.

## Current Roles

### `symbol_read_model.py`

Role today:

- deterministic cumulative symbol summary
- lightweight runtime-facing aggregation
- currently consumed directly by strategist-side deterministic context

Strengths:

- simple deterministic contract
- already wired into runtime
- small enough for strategist-side use

Weaknesses:

- built by scanning trade directories each time
- limited field richness
- not aligned with the new symbol-memory contract
- not written as a persisted canonical memory surface

### `symbol_trade_report.py`

Role today:

- richer per-symbol operator/history report
- writes:
  - `symbol_trade_report.json`
  - `symbol_trade_report.md`
  - `trade_history.json`
  - `daily_index.json`
  - `latest_snapshot.json`

Strengths:

- richer history index
- better pattern/explanation material
- better suited as source material

Weaknesses:

- originally operator-facing, not scanner-ready
- not consumed directly by runtime

### `symbol_memory.json`

Role now:

- compact deterministic runtime packet added beside symbol trade report
- intended for:
  - scanner deterministic priors
  - selected-symbol strategist refresh
  - long-hold refresh support

Strengths:

- matches the new runtime memory direction
- persisted canonical-ish memory surface
- narrower than full symbol report

Weaknesses:

- not yet consumed by runtime
- overlaps with `symbol_read_model.py`

## Overlap Matrix

| Capability | `symbol_read_model.py` | `symbol_memory.json` | Decision |
|---|---|---|---|
| trade count | yes | yes | keep in memory surface, allow read-model compatibility for now |
| win/loss counts | yes | partially via `trade_stats` | standardize on memory surface shape |
| win rate | yes | yes | standardize on memory surface |
| avg pnl / avg return | yes | yes | standardize on memory surface |
| avg hold duration | yes | yes | standardize on memory surface |
| dominant playbook | yes | derivable | migrate toward memory surface |
| dominant entry reason | yes | not explicit yet | keep read-model for now |
| dominant exit reason | yes | partially via dominant failure axis | keep read-model for now |
| dominant monitor blocker | yes | partially via repeated blockers | migrate later |
| repeated failure pattern | yes | yes, richer contract direction | migrate toward memory surface |
| playbook-specific stats | weak | yes | memory surface wins |
| execution risk | no | reserved field, not filled yet | memory surface target |
| refresh suitability | weak | yes | memory surface target |
| persisted canonical artifact | no | yes | memory surface wins |

## Recommended Role Split

### Short Term

Keep both.

Use this split:

- `symbol_read_model.py`
  - compatibility runtime adapter
  - existing strategist deterministic consumer

- `symbol_memory.json`
  - target runtime memory surface
  - future scanner / selected-symbol refresh input

### Medium Term

Refactor `symbol_read_model.py` so it becomes a reader/adapter over persisted symbol memory where possible.

Target direction:

1. generate `symbol_memory.json`
2. teach `build_symbol_read_model(...)` to prefer `symbol_memory.json`
3. only fall back to raw trade aggregation if persisted memory is missing

This keeps existing consumers stable while reducing duplicated logic.

### Long Term

Once all runtime consumers migrate:

- `symbol_read_model.py` should become a thin compatibility layer
- or be absorbed into a dedicated runtime-memory reader module

But it should not be removed before strategist and operator consumers are moved.

## Immediate Decision

Do not delete `symbol_read_model.py`.

Do this instead:

1. preserve existing strategist/runtime consumer behavior
2. treat `symbol_memory.json` as the future canonical symbol-memory surface
3. migrate consumers gradually
4. shrink `symbol_read_model.py` later into a compatibility reader

## Next Safe Slice

The next safe implementation slice is:

1. teach `build_symbol_read_model(...)` to read `reports/symbols/<symbol>/symbol_memory.json` if it exists
2. normalize its output into the current read-model contract
3. keep raw aggregation as fallback

That avoids breaking strategist while stopping further duplication.
