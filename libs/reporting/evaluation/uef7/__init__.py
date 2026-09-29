"""UEF-7 -- Alpha Board Normalization.

Produces one deterministic, comparison-ready NORMALIZED VIEW over the
frozen Alpha Research Board v2 (``libs/reporting/alpha_research_board``).
Read-only against the board: never adds a field to its frozen
``ROW_COLUMNS``, never calls ``canonicalize_board``/``CANDIDATE_REGISTRY``/
``CANDIDATE_IDS`` differently, never mutates any candidate row, metric,
decision, or promotion state.

UEF-7 owns row/metric/source normalization, source-provenance overlap
grouping, and explicit population-proof/independence status labeling. It
never performs fair comparison, ranking, winner selection, promotion, or
strategy tuning -- those are explicitly out of scope (UEF-8 and beyond).
"""
