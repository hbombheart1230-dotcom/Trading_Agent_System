"""UEF-4B-2 -- Q12 (BTC-led Woori Technology Investment) shared adapter layer.

Q12 has THREE legacy calculators, per UEF-4A's inventory (Table B) and
re-verified directly against real source here:

- **Calc1** (`libs/reporting/baseline_btc_woori_tech/forward_returns.py::
  attach_forward_returns`) -- calls Q10 Semiconductor's OWN
  `attach_baseline_forward_returns` directly, on Q12's single fixed
  candidate (symbol `041190`). NOT a new semantic family -- reuses the
  frozen `forward_measurement_adapter` generic layer verbatim (see
  `build_calc1_episode` below). No new adapter family is created for it.
- **Calc2** -- `hypothesis_forward_adapter.py` (this package, sibling
  module).
- **Calc3** -- `vnext_completeness_adapter.py` (this package, sibling
  module).

This module holds what Calc2 and Calc3 both need (the shared "one
(trading_date, entry_method) sample" identity -- both read the exact same
`entry_methods` feature dict, per `hypothesis_pipeline.py`/
`vnext/pipeline.py`, `forward(day, record['features']['entry_methods']
[method], ...)`) plus Calc1's own thin translation layer.

SOURCE AUTHORITY (verified against real source, not only the inventory
doc):
- `libs/reporting/baseline_btc_woori_tech/contracts.py` -- `PROGRAM_ID`,
  `TARGET_SYMBOL="041190"`, `TARGET_TICKER`, `HYPOTHESIS_CONTRACT_ID`.
- `libs/reporting/baseline_btc_woori_tech/forward_returns.py::attach_forward_returns`
  -- Calc1's own decision->candidate remapping (`local_features`, single
  fixed-rank-1 candidate).
- `libs/reporting/baseline_btc_woori_tech/strategy.py::build_decision_snapshot`
  -- `decision_id = f"BTW_{day}_{as_of_epoch}"`, top-level `eligible`/
  `action`/`reason` (`"entry_condition_failed"` when the BTC signal IS
  available but ENTRY_RULES are not all satisfied -- distinct from
  `btc.get("reason")`/`"btc_signal_unavailable"` when the BTC signal never
  resolved at all).
- `libs/reporting/evaluation/canonical/forward/profiles.py::
  build_q12_calc1_shared_engine_profile` -- the frozen UEF-2A profile
  (7 checkpoints: +5/15/30/60m via Python free-variable resolution onto
  Q10's own `HORIZONS`, +120/180m, EOD; GROSS_ONLY).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from libs.reporting.evaluation.canonical.contracts import EventOrigin, ExecutionMode
from libs.reporting.evaluation.canonical.identity import (
    DerivedFieldKind,
    DerivedIdentityPart,
    EventRef,
)
from libs.reporting.evaluation.canonical.record import EpisodeRecord, Provenance
from libs.reporting.evaluation.canonical.forward import PriceCandidate
from libs.reporting.evaluation.canonical.forward.engine import CanonicalObservation, ResolvedReference
from libs.reporting.evaluation.canonical.forward.profiles import build_q12_calc1_shared_engine_profile

from .forward_measurement_adapter import (
    ForwardMeasurementAdapterError,
    build_forward_measurement_episode,
    build_forward_measurement_event_ref,
)


class Q12AdapterError(ForwardMeasurementAdapterError):
    """Raised for a Q12 legacy-input problem (any calculator) -- fail fast, never repair."""


SOURCE_NAMESPACE = "baseline_btc_woori_tech_q12"
TARGET_SYMBOL = "041190"
TARGET_TICKER = "041190.KQ"
CALC1_HYPOTHESIS_ID = "Q12_BTC_WOORI_TECH_BASELINE"  # real contracts.py::PROGRAM_ID


def _finite_float(value: Any, *, field: str) -> float:
    """FIX1 (Fix C): every load-bearing numeric must be a real, finite
    number -- NaN/+inf/-inf are never silently passed through to a
    canonical observation (no later-arithmetic-will-catch-it reliance)."""

    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise Q12AdapterError(f"candles_to_observations: {field}={value!r} is not a real number") from exc
    if not math.isfinite(number):
        raise Q12AdapterError(f"candles_to_observations: {field}={value!r} is not finite (NaN/inf are never valid)")
    return number


def candles_to_observations(rows: Sequence[Mapping[str, Any]]) -> list[CanonicalObservation]:
    """Shared OHLCV-dict -> `CanonicalObservation` translation for all three
    Q12 calculators. A deliberate small, Q12-local copy of the same
    pattern `q10_semiconductor.py::_candles_to_observations` uses -- NOT a
    call into that frozen (UEF-4B-1) module. `forward_measurement_adapter.py`
    never grew a public version of this helper, and UEF-4B-1's own
    correctness is unaffected either way (option B, not C, per this
    task's own Calc1-reuse decision tree: no frozen-4B1 contradiction
    exists, only a missing convenience -- not grounds to reopen a frozen
    file). FIX1's lesson is preserved here too: an invalid/non-positive
    timestamp is REJECTED, never silently dropped.

    FIX1 (Fix C) hardening -- generic, structural validation shared by all
    three calculators, never a Calc-specific branch:
    - `open`/`high`/`low`: NaN/inf/negative are rejected outright (never a
      legitimate sentinel for ANY of Calc1/2/3 -- the real upstream
      candle loader, `baseline_samsung_hynix/data_provider.py::
      _normalize_rows`, never produces a negative price either). Exactly
      `0.0` is passed through UNRESOLVED (never rejected here): for Calc1
      it is a genuine `PriceCandidate` chain-fallback trigger already
      declared in the frozen profile
      (`_chain(PriceCandidate.BAR_HIGH, PriceCandidate.REFERENCE_PRICE)`,
      `resolve_ordered_price`'s own `_is_valid_price` correctly treats 0
      as invalid and falls through the chain); for Calc2 it is Calc2's
      OWN legacy sentinel, already resolved to a real, positive value by
      `hypothesis_forward_adapter.py`'s own pre-processing BEFORE this
      function ever sees the row -- this function never has to special-case
      Calc2 itself (no `if calc2 ...` branch here).
    - `close`: the one field this system's own real candle-loading
      contract requires strictly positive
      (`_normalize_rows`'s own `close<=0: continue` filter -- such a row
      never legitimately reaches ANY consumer) -- rejected outright if
      present and not finite-positive.
    - `volume`: NaN/inf/negative rejected; exactly `0.0` is allowed
      through (none of Calc1/2/3's own checkpoint/excursion logic treats
      volume as load-bearing -- confirmed by direct source read of
      `quant_shadow_forward_outcomes.py`/`hypothesis_forward.py`/
      `vnext/outcomes.py`, none of which reference `row.get('volume')` at
      all; unlike Q10 Index Calc F's own `require_positive_volume` rule,
      no Q12 calculator declares one).
    """

    observations: list[CanonicalObservation] = []
    for row in rows:
        ts = int(row.get("ts") or 0)
        if ts <= 0:
            raise Q12AdapterError(
                f"candles_to_observations: candle has invalid timestamp ts={ts!r} (raw={row.get('ts')!r}) -- "
                "a non-positive candle timestamp is rejected outright, never silently dropped"
            )
        fields: dict[PriceCandidate, float] = {}
        for key, candidate in (
            ("open", PriceCandidate.BAR_OPEN),
            ("high", PriceCandidate.BAR_HIGH),
            ("low", PriceCandidate.BAR_LOW),
        ):
            value = row.get(key)
            if value is None:
                continue
            number = _finite_float(value, field=key)
            if number < 0:
                raise Q12AdapterError(f"candles_to_observations: {key}={number!r} is negative -- never a legitimate sentinel or valid price")
            fields[candidate] = number
        close_value = row.get("close")
        if close_value is not None:
            close_number = _finite_float(close_value, field="close")
            if close_number <= 0:
                raise Q12AdapterError(f"candles_to_observations: close={close_number!r} must be strictly positive")
            fields[PriceCandidate.BAR_CLOSE] = close_number
        volume_value = row.get("volume")
        volume: float | None = None
        if volume_value is not None:
            volume = _finite_float(volume_value, field="volume")
            if volume < 0:
                raise Q12AdapterError(f"candles_to_observations: volume={volume!r} is negative -- never valid")
        observations.append(CanonicalObservation(timestamp=ts, fields=fields, volume=volume))
    return observations


def build_entry_method_event_ref(*, trading_date: str, entry_method: str) -> EventRef:
    """Identity shared by Calc2 and Calc3: one (trading_date, TARGET_SYMBOL,
    entry_method) local-equity entry point. Both calculators read the
    EXACT SAME `entry_methods[method]` feature (one real local reference
    event) -- sharing this `EventRef` and differentiating the two
    calculators' own `EpisodeRecord`s via `hypothesis_id` (Calc2 vs Calc3
    each declare their own) is the frozen-correct UEF-1 pattern for
    "same real event, evaluated under two different research protocols"
    (`classify_duplicate_relation`'s own `LEGITIMATE_MULTI_HYPOTHESIS`
    case), never a reason to invent a second identity system.
    """

    return build_forward_measurement_event_ref(
        source_namespace=SOURCE_NAMESPACE,
        trading_date=trading_date,
        symbol=TARGET_SYMBOL,
        extra_fields={"entry_method": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=entry_method)},
    )


# =========================================================================
# Calc1 -- reuses the frozen forward_measurement_adapter generic layer
# =========================================================================


@dataclass(frozen=True)
class Q12Calc1Candidate:
    """One Q12 Calc1 decision's single fixed candidate (symbol=041190),
    parsed from a real `baseline_btc_woori_decisions.json` decision row."""

    decision_id: str
    trading_date: str
    eligible: bool
    action: str
    available: bool
    baseline_epoch: int | None
    baseline_price: float | None


def parse_calc1_decisions(decisions: Sequence[Mapping[str, Any]]) -> list[Q12Calc1Candidate]:
    """Parse real `baseline_btc_woori_decisions.json`-shaped decision rows
    (`strategy.py::build_decision_snapshot`'s own output). Fail-fast on
    missing/invalid load-bearing fields."""

    out: list[Q12Calc1Candidate] = []
    for decision in decisions:
        decision_id = str(decision.get("decision_id") or "").strip()
        if not decision_id:
            raise Q12AdapterError("parse_calc1_decisions: decision.decision_id is required")
        trading_date = str(decision.get("day") or "").strip()
        if not trading_date:
            raise Q12AdapterError(f"parse_calc1_decisions: decision {decision_id!r} has no 'day'")
        local_features = decision.get("local_features")
        local_features = local_features if isinstance(local_features, Mapping) else {}
        available = bool(local_features.get("available"))
        baseline_epoch = local_features.get("baseline_epoch") if available else None
        baseline_price = local_features.get("baseline_price") if available else None
        if available and (baseline_epoch is None or baseline_price is None or float(baseline_price) <= 0):
            raise Q12AdapterError(
                f"parse_calc1_decisions: decision {decision_id!r} declares local_features.available=true "
                "but baseline_epoch/baseline_price is missing/invalid -- contradictory source fields"
            )
        out.append(
            Q12Calc1Candidate(
                decision_id=decision_id,
                trading_date=trading_date,
                eligible=bool(decision.get("eligible")),
                action=str(decision.get("action") or "").strip(),
                available=available,
                baseline_epoch=int(baseline_epoch) if baseline_epoch is not None else None,
                baseline_price=float(baseline_price) if baseline_price is not None else None,
            )
        )
    return out


def build_calc1_episode(candidate: Q12Calc1Candidate, minute_rows: Sequence[Mapping[str, Any]]) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one Q12 Calc1 decision.

    Delegates 100% to the frozen, generic `forward_measurement_adapter`
    layer (`build_forward_measurement_episode`) with the frozen UEF-2A
    `build_q12_calc1_shared_engine_profile()` -- NO new adapter family,
    NO duplicated identity/checkpoint/aggregation logic. `NEW CALC1
    ADAPTER FAMILY = NO`; `Q10 SEMANTIC REUSE = YES`.
    """

    if not candidate.available or candidate.baseline_epoch is None or candidate.baseline_price is None:
        raise Q12AdapterError(
            f"build_calc1_episode: candidate decision_id={candidate.decision_id!r} has no resolved baseline "
            "reference (local_features.available=false) -- caller must treat this candidate as a MISSING "
            "population member instead of building an episode for it"
        )
    observations = candles_to_observations(minute_rows)
    resolved_reference = ResolvedReference.single(
        origin=EventOrigin.CANDIDATE, timestamp=candidate.baseline_epoch, price=candidate.baseline_price,
    )
    event_ref = build_forward_measurement_event_ref(
        source_namespace=SOURCE_NAMESPACE,
        trading_date=candidate.trading_date,
        symbol=TARGET_SYMBOL,
        extra_fields={"decision_id": DerivedIdentityPart(kind=DerivedFieldKind.RAW, value=candidate.decision_id)},
    )
    return build_forward_measurement_episode(
        source_namespace=SOURCE_NAMESPACE,
        hypothesis_id=CALC1_HYPOTHESIS_ID,
        execution_mode=ExecutionMode.SHADOW,
        trading_date=candidate.trading_date,
        symbol=TARGET_SYMBOL,
        horizon_origin=EventOrigin.CANDIDATE,
        event_ref=event_ref,
        resolved_reference=resolved_reference,
        observations=observations,
        profiles=(("baseline_btc_woori_tech_calc1_shared_engine", build_q12_calc1_shared_engine_profile()),),
        provenance=Provenance(
            legacy_program="baseline_btc_woori_tech_calc1_shared_engine",
            legacy_schema="baseline_btc_woori_decisions.v2",
            source_artifact="reports/evaluation/baseline_btc_woori_tech/<day>/baseline_btc_woori_forward_returns.json",
            source_function="attach_forward_returns -> attach_baseline_forward_returns",
        ),
        metadata={
            "decision_id": candidate.decision_id,
            "eligible": candidate.eligible,
            "action": candidate.action,
            "ticker": TARGET_TICKER,
        },
    )


__all__ = [
    "Q12AdapterError",
    "SOURCE_NAMESPACE",
    "TARGET_SYMBOL",
    "TARGET_TICKER",
    "CALC1_HYPOTHESIS_ID",
    "candles_to_observations",
    "build_entry_method_event_ref",
    "Q12Calc1Candidate",
    "parse_calc1_decisions",
    "build_calc1_episode",
]
