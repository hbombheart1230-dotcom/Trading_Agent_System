"""Legacy reader for the ``*_forward_returns.json`` family shape.

Both Q10 Semiconductor (``baseline_samsung_hynix_forward_returns.json``) and
Q12 Calc1 (``baseline_btc_woori_forward_returns.json``) share the exact same
legacy schema shape:  ``summary.horizons[] -> {view}_{gross|net}`` blocks
with ``count/win_count/loss_count/flat_count/win_rate/average_return_pct/
average_gain_pct/average_loss_pct/profit_factor/expectancy_pct/
maximum_drawdown_pct``.

This reader is discovery-glob-identical to the UEF-5.1/UEF-4 registry scope
for these two families (see ``libs/reporting/evaluation/uef5/
clean_evidence_rules.py``) so the legacy side and the canonical side are
built from the SAME source population by construction -- this module never
invents its own discovery scope.

Every artifact this module reads is hashed (sha256 of the raw file bytes,
the exact same digest UEF-5.2's own ``input_manifest.json`` records as
``primary_source_hash``) so a UEF-5.3 dual run can (a) build a deterministic
legacy input manifest and (b) verify its own hash against UEF-5.2's
previously-recorded one (see ``canonical_run.CanonicalRun.
recorded_source_hash_for_path``).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional


# view name -> legacy JSON key prefix (canonical Q10SemiconductorView enum
# values, as used by libs/reporting/evaluation/uef5/historical_recompute.py)
VIEW_KEY_PREFIX = {
    "TOP1": "top1",
    "BOTH_SYMBOL_AVERAGE": "both_symbol_average",
    "ELIGIBLE_ENTRIES": "eligible_entries",
}

FAMILY_GLOBS = {
    "q10_semiconductor": "reports/evaluation/baseline_samsung_hynix/*/baseline_samsung_hynix_forward_returns.json",
    "q12_calc1": "reports/evaluation/baseline_btc_woori_tech/*/baseline_btc_woori_forward_returns.json",
}


@dataclass(frozen=True)
class LegacyArtifact:
    """Content identity of one legacy source artifact actually consumed."""

    path: str  # repo-root-relative
    sha256: str
    reader_profile_id: str  # e.g. "legacy_forward_returns.v1"
    row_count: Optional[int]


@dataclass(frozen=True)
class LegacyHorizonView:
    """One (view, gross|net) cell of one horizon of one day's legacy summary."""

    path: str
    content_hash: str
    day: str
    horizon: str
    view: str
    cost_treatment: str  # "gross" | "net"
    count: Optional[int]
    win_count: Optional[int]
    loss_count: Optional[int]
    flat_count: Optional[int]
    win_rate: Optional[float]
    average_return_pct: Optional[float]
    profit_factor: Optional[float]
    maximum_drawdown_pct: Optional[float]
    member_ids: Optional[frozenset] = None
    """Legacy member/decision-identity set for this cell's population, when
    the legacy artifact persists one. The real ``summary.horizons[]``
    artifact this reader parses does NOT persist per-row decision
    identities at this aggregated level -- production use of this reader
    therefore always leaves this ``None`` (an honest limitation, not a bug:
    see ``divergence_classifier.population_identity_proven``, which treats
    ``None`` as "legacy member IDs unavailable", never as a false proof).
    This field exists so the population-identity proof gate itself is
    testable and ready for a future legacy reader that DOES expose member
    identities, without inventing or reconstructing any today."""


READER_PROFILE_ID = "legacy_forward_returns.v1"


def iter_legacy_forward_returns_artifacts(repo_root: Path, family_key: str) -> Iterator[tuple]:
    """Yields (path, parsed_json_or_None, parse_error_or_None,
    LegacyArtifact_or_None) for every artifact matching this family's
    registry-scope glob, discovered in the exact same way the canonical
    UEF-5.1/UEF-4 registry discovers it."""

    glob_pattern = FAMILY_GLOBS[family_key]
    for path in sorted(repo_root.glob(glob_pattern)):
        raw_bytes = path.read_bytes()
        content_hash = hashlib.sha256(raw_bytes).hexdigest()
        try:
            doc = json.loads(raw_bytes.decode("utf-8"))
            identity = LegacyArtifact(
                path=str(path.relative_to(repo_root)).replace("\\", "/"),
                sha256=content_hash,
                reader_profile_id=READER_PROFILE_ID,
                row_count=doc.get("row_count") if isinstance(doc, dict) else None,
            )
            yield path, doc, None, identity
        except Exception as exc:  # noqa: BLE001 - legacy artifact may be malformed; report, don't crash
            identity = LegacyArtifact(
                path=str(path.relative_to(repo_root)).replace("\\", "/"),
                sha256=content_hash,
                reader_profile_id=READER_PROFILE_ID,
                row_count=None,
            )
            yield path, None, exc, identity


def extract_horizon_views(path: Path, doc: dict, content_hash: str, repo_root: Optional[Path] = None) -> list:
    """Flattens ``summary.horizons[]`` into one row per (horizon, view,
    cost_treatment) cell. Returns an empty list (never fabricates rows) if
    the document has no ``summary.horizons``.

    ``rel_path`` is computed relative to ``repo_root`` (when given) so it
    matches the repo-root-relative paths UEF-5.2's own
    ``run_manifest.json['artifact_outcomes']`` and ``aggregates.json``
    provenance already use -- the join key between the legacy and
    canonical sides depends on this being the SAME string on both sides.
    """

    day = doc.get("day", "")
    horizons = ((doc.get("summary") or {}).get("horizons")) or []
    rows = []
    if repo_root is not None:
        try:
            rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
        except ValueError:
            rel_path = str(path).replace("\\", "/")
    else:
        rel_path = str(path).replace("\\", "/")
    for h in horizons:
        horizon_label = h.get("horizon", "")
        for view, prefix in VIEW_KEY_PREFIX.items():
            for cost_treatment in ("gross", "net"):
                block = h.get(f"{prefix}_{cost_treatment}")
                if block is None:
                    continue
                rows.append(
                    LegacyHorizonView(
                        path=rel_path,
                        content_hash=content_hash,
                        day=day,
                        horizon=horizon_label,
                        view=view,
                        cost_treatment=cost_treatment,
                        count=block.get("count"),
                        win_count=block.get("win_count"),
                        loss_count=block.get("loss_count"),
                        flat_count=block.get("flat_count"),
                        win_rate=block.get("win_rate"),
                        average_return_pct=block.get("average_return_pct"),
                        profit_factor=block.get("profit_factor"),
                        maximum_drawdown_pct=block.get("maximum_drawdown_pct"),
                    )
                )
    return rows
