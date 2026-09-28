"""Shared, UEF-independent market-data provenance contract (acquisition boundary infrastructure).

Not part of the seven-agent runtime topology and not a strategy/Q namespace. Acquisition components
(e.g. `libs/research/post_reclaim_alpha/kiwoom_history.py`) issue `MarketDataReceipt`s here; UEF-5.2
(`libs/reporting/evaluation/uef5/candle_authority.py`) verifies them. This package never imports UEF
code (UEF depends on this package, never the reverse).
"""
