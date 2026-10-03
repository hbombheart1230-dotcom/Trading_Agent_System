"""Legacy reader for Q11 v2's ``opportunity_engine_virtual_trades.json``.

Semantic equivalence to canonical ``q11_virtual_probe`` / horizon ``EXIT``
was established by reading the actual code, not inferred from names (Core
Correction 1 item 16):

- Discovery glob and family/program identity match UEF-5.1's own registry
  scope exactly (``libs/reporting/evaluation/uef5/clean_evidence_rules.py``,
  ``F_Q11`` / ``Q11_PROGRAM`` / ``Q11_V2_SCHEMA``), so the legacy and
  canonical sides are built from the same source population by construction.
- ``_pipeline_q11_v2`` (historical_recompute.py) builds one canonical
  aggregate per horizon in ``_Q11_HORIZONS = ("+5m","+15m","+30m","+60m",
  "EOD","EXIT")`` via ``q11.checkpoint_to_net_or_cost_included_member`` --
  i.e. NET_OR_COST_INCLUDED semantics (the source's own net figure is used
  as-is, no separate cost policy applied). The ``EXIT`` horizon is built
  from each trade's own realized exit checkpoint, which corresponds
  EXACTLY to legacy's own per-trade ``net_return_pct`` field (the trade's
  actual entry/exit outcome, already cost-inclusive per the artifact's own
  persisted ``cost_model``) -- NOT any of the ``forward_returns{}`` horizon
  sub-fields (which track a *hypothetical* forward path from entry, a
  different population Q11 v2's ``+5m``/``+15m``/... horizons compare
  against, not wired by this delivery).
- ``Q11 v2`` has NO per-view split at all (unlike Q10 Semiconductor's
  TOP1/BOTH_SYMBOL_AVERAGE/ELIGIBLE_ENTRIES) and NO separate gross figure
  (the source schema persists only ``net_return_pct``) -- there is exactly
  ONE population per trading day: all of that day's virtual trades.
- Legacy's own summary provides ``trade_count``/``win_rate``/
  ``profit_factor``/``average_net_return_pct`` but NOT a win/loss/flat
  breakdown or a maximum-drawdown figure. win/loss/flat counts are derived
  directly from the raw ``trades[].net_return_pct`` array using the exact
  WIN/LOSS/FLAT rule the frozen UEF-3A contract documents as universal
  (``net_return > 0 -> WIN``, ``< 0 -> LOSS``, ``== 0 -> FLAT``) -- this is
  applying an existing, cited rule to real data, never inventing a new
  metric. Maximum drawdown has no legacy equivalent for Q11 at all (the
  source artifact never persists one) and is therefore never compared for
  this family (field-level NON_COMPARABLE, stated explicitly).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

FAMILY_GLOB_Q11 = "reports/evaluation/opportunity_engine_shadow/*/opportunity_engine_virtual_trades.json"
READER_PROFILE_ID = "legacy_opportunity_engine.v1"


@dataclass(frozen=True)
class LegacyArtifactIdentity:
    path: str
    sha256: str
    reader_profile_id: str
    row_count: Optional[int]


@dataclass(frozen=True)
class LegacyQ11ExitDay:
    """The single, undifferentiated per-day EXIT population for Q11 v2."""

    path: str
    content_hash: str
    day: str
    trade_count: int
    win_count: int
    loss_count: int
    flat_count: int
    win_rate: Optional[float]
    profit_factor: Optional[float]
    average_net_return_pct: Optional[float]


def iter_legacy_q11_artifacts(repo_root: Path) -> Iterator[tuple]:
    """Yields (path, parsed_json_or_None, parse_error_or_None,
    LegacyArtifactIdentity)."""

    for path in sorted(repo_root.glob(FAMILY_GLOB_Q11)):
        raw_bytes = path.read_bytes()
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
        try:
            doc = json.loads(raw_bytes.decode("utf-8"))
            identity = LegacyArtifactIdentity(
                path=rel_path, sha256=content_hash, reader_profile_id=READER_PROFILE_ID,
                row_count=doc.get("trade_count") if isinstance(doc, dict) else None,
            )
            yield path, doc, None, identity
        except Exception as exc:  # noqa: BLE001
            identity = LegacyArtifactIdentity(path=rel_path, sha256=content_hash, reader_profile_id=READER_PROFILE_ID, row_count=None)
            yield path, None, exc, identity


def extract_q11_exit_day(path: Path, doc: dict, content_hash: str, repo_root: Optional[Path] = None) -> LegacyQ11ExitDay:
    if repo_root is not None:
        try:
            rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel_path = str(path).replace("\\", "/")
    else:
        rel_path = str(path).replace("\\", "/")

    summary = doc.get("summary") or {}
    trades = doc.get("trades") or []
    win_count = 0
    loss_count = 0
    flat_count = 0
    for t in trades:
        r = t.get("net_return_pct") if isinstance(t, dict) else None
        if not isinstance(r, (int, float)):
            continue
        if r > 0:
            win_count += 1
        elif r < 0:
            loss_count += 1
        else:
            flat_count += 1

    return LegacyQ11ExitDay(
        path=rel_path,
        content_hash=content_hash,
        day=doc.get("day", ""),
        trade_count=int(summary.get("trade_count", len(trades)) or 0),
        win_count=win_count,
        loss_count=loss_count,
        flat_count=flat_count,
        win_rate=summary.get("win_rate"),
        profit_factor=summary.get("profit_factor"),
        average_net_return_pct=summary.get("average_net_return_pct"),
    )
