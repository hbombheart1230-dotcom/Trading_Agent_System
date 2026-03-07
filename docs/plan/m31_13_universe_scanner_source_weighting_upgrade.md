# M31-13 Universe/Scanner Source Weighting Upgrade

- Date: 2026-03-07
- Goal: strengthen candidate universe construction with sector source and source-level explainability while preserving existing scanner contracts.

## What Changed

1. Universe builder source expansion and weighting
- File: `libs/strategies/universe_builder.py`
- Added source weight policy map:
  - `policy.candidate_source_weights`
  - supported keys: `held_position`, `watchlist`, `sector`, `theme`, `condition`, `liquidity`, `market_rank`
- Added sector source extraction:
  - `state.sector_symbols`, `policy.sector_symbols`
  - `state.sector_map` / `policy.sector_map` + `sector_filter`
  - `sector_or_theme_symbols` aliases
- Added alias support for held/watchlist sources:
  - held: `held_symbols`, `held_positions`
  - watchlist: `watchlist`, `manual_watchlist`

2. Candidate provenance detail expansion (additive)
- Universe output now includes:
  - `source_scores: {source: score_contribution}`
  - `source_count: int`
- Existing fields are unchanged:
  - `symbol`, `score`, `sources`, `why`

3. Strategist/scanner metadata propagation
- File: `graphs/nodes/strategist_node.py`
  - propagate `source_scores`, `source_count` from `universe_candidates` into `state.candidates`
- File: `graphs/nodes/scanner_node.py`
  - include `candidate.source_scores`, `candidate.source_count` in `scan_results[*].candidate`

## Compatibility

- Existing `candidates` contract remains compatible (`symbol`, `why` preserved).
- Existing scanner ranking logic and output shape remain valid.
- Changes are additive and do not weaken approval/guard execution model.

## Tests

- Updated:
  - `tests/test_strategy_universe_builder.py`
    - verifies `source_scores` / `source_count`
    - verifies sector filter + source weight override behavior
  - `tests/test_scanner_universe_candidate_metadata.py`
    - verifies scanner candidate metadata carries `source_scores` / `source_count`

- Full suite:
  - `498 passed`
