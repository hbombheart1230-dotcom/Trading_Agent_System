"""UEF-4 -- Legacy Adapter Layer.

Converts existing legacy evaluation artifacts (Q9-Q18, Opening, baselines
-- see `docs/research/uef4_legacy_family_inventory.md` for the full
per-family classification) into the frozen UEF-1/2A/2B/3A/3B/3C canonical
contracts, without changing legacy strategy behavior and without adding
any program-specific branch to the frozen core.

Each module in this package is named after the SEMANTIC adapter family it
implements (e.g. `forward_measurement_adapter`), per UEF-4A's own
6-family classification (Table B), not after a Q number. A module may
still contain Q-specific legacy schema knowledge when unavoidable (e.g.
`q10_semiconductor.py` knows the real `baseline_samsung_hynix` artifact
shape) -- the frozen `canonical/` core never does.

This package is read-only with respect to legacy evidence: it never
writes back to a legacy artifact file, never mutates broker/runtime
state, and is not imported by any production/runtime module (offline
canonicalization only).
"""

from __future__ import annotations

__all__: list[str] = []
