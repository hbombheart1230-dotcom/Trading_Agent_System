# M31-5 Universe Builder Upgrade

- Date: 2026-03-07
- Goal: upgrade candidate selection from single-source fallback into multi-source universe construction.

## Added

1. `libs/strategies/universe_builder.py`
   - merges candidate sources:
     - held positions
     - manual watchlist
     - theme symbols
     - market-rank symbols
     - condition-search symbols
     - liquidity symbols (optional injection)
   - ranks symbols and returns Top-K with `score`, `sources`, `why`

2. `graphs/nodes/strategist_node.py`
   - integrates universe builder (`use_universe_builder`)
   - keeps legacy injection priority (`candidates`, `universe`, `candidate_symbols`)
   - writes `state["universe_candidates"]` for observability
   - preserves existing output contract (`candidates` with `symbol`, `why`)

3. `graphs/nodes/scanner_node.py`
   - consumes candidate metadata (`rank_score`, `universe_score`, `sources`)
   - records source metadata into scan result rows

## Env / Policy

- `USE_UNIVERSE_BUILDER` (default true)
- `UNIVERSE_REQUIRE_CONDITION` (default false)

## Validation

- `tests/test_strategy_universe_builder.py`
  - verifies multi-source merge behavior
  - verifies strategist integration contract remains stable
