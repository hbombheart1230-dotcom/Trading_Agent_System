"""UEF-5.3 Historical Dual Run.

Compares the legacy (pre-UEF) evaluation outputs against the FROZEN UEF-5.2
canonical historical recompute output for the SAME historical evidence, and
classifies every material difference.

This package is READ-ONLY with respect to UEF-1 through UEF-5.2: it never
imports for write, never mutates any frozen file, and never re-derives a
canonical metric using its own formula. It only *reads* two already-produced
outputs (the legacy per-day artifacts under ``reports/evaluation/...`` and a
frozen UEF-5.2 ``historical_recompute`` run under
``reports/evaluation/uef5/historical_recompute/<run_id>/``) and reports where
they agree, where they differ and explain why, and where they cannot be
compared at all.

It is explicitly NOT a new evaluation engine: it builds no episodes, no
aggregates, and computes no win/loss/profit-factor/drawdown figure of its
own for the canonical side -- those numbers are read verbatim from the
UEF-5.2 output. The only numbers this package computes are the *dual-run
bookkeeping* counts themselves (how many units matched, diverged, were
blocked, etc).
"""
