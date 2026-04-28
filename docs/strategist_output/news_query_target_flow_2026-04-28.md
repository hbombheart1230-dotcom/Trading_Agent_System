# Strategist News Query Target Flow

## Purpose

News collection is not performed by the Strategist LLM.
The runtime calls the configured news provider, currently `naver` by default, before the LLM prompt is built.
The Strategist LLM receives collected headlines, sentiment signals, and source diagnostics as input evidence.

## Boundary

```text
strategist_node
-> build news_query_targets
-> collect_news_items(provider=naver)
-> score_news_sentiment_signal
-> pass market_news_sample / candidate_news_sample to Strategist LLM
-> scanner ranks symbols
-> report reuses collected news evidence
```

The Scanner must not trigger a fresh post-selection news search.
If the final selected symbol needs news evidence, the report should reuse the already collected news pool.

## Query Target Contract

The news query list should be assembled from these layers:

1. Explicit operator/runtime targets: `state.news_query_targets`, `policy.news_query_targets`, `NEWS_QUERY_TARGETS`.
2. Kiwoom theme hints: top Kiwoom themes from `theme_strength_packet` and Strategist-selected theme hints when available.
3. Market core targets: KOSPI/KOSDAQ/US market/macro terms, chosen by global score, macro risk, VIX, index trend, and breadth.
4. Macro event targets: `macro_events`, `global_events`, `major_events`.

Theme terms should be added before broad static market terms when available.
This prevents every run from collapsing into only KOSPI/KOSDAQ/US market/macro queries.

## Candidate News Contract

Candidate news collection should cover:

- current deterministic candidate symbols.
- a bounded number of component symbols from top Kiwoom themes.

This gives the Scanner and report a reusable news pool even when the final Scanner-selected symbol was not in the initial legacy candidate list.

## Artifact Fields

Strategist output should expose:

```json
{
  "news_collection_policy": {
    "provider": "naver",
    "market_query_targets": [],
    "candidate_symbols_requested": [],
    "theme_component_symbols_requested": [],
    "collection_symbols": [],
    "post_scanner_requery": false,
    "reuse_policy": "reuse_pre_scanner_news_pool"
  }
}
```

Reports should distinguish:

- market news: broad market and macro targets.
- theme news: Kiwoom theme-derived query targets.
- candidate news: pre-scanner candidate and theme-component symbol news.
- post-selection news: must be `none` unless an operator explicitly requests a manual inspection pass.
