"""UEF-2A BOUNDARY CLOSURE -- generic canonical forward-calculation-recipe vocabulary.

Four prior audits (initial, Fix1, Fix2, Semantic Authority Reset) each
closed some findings while leaving one design question unanswered: which
semantics belong to the GENERIC forward-measurement core (this module +
`policy.py`) versus which are PROGRAM-SPECIFIC research algorithms that
belong only in a declarative semantic profile (`profiles.py`), never in
the generic contract itself. This module's own vocabulary must remain
readable without knowing any program name (Q9/Q10/Q11/Q12/Opening) --
every member below traces to a specific, re-verified file:line in a real
legacy calculator, but is phrased as a GENERIC measurement primitive.

Source authority order for every claim in this module (unchanged):
real legacy source code > real artifact > documented source constant >
this contract > any existing test. A test that recorded a value different
from re-verified source was always wrong, never authority.

Still computes nothing -- UEF-2B owns the resolver/engine, and UEF-2B's own
generic primitive set (`resolve_target`/`resolve_observation`/
`resolve_ordered_price`/`validate_evidence`/`validate_completeness`/
`resolve_missing`/`resolve_session_close`/`resolve_forward_session`/
`resolve_excursion`/`calculate_gross_return`) must never require a
program-specific function (e.g. a retracement-scan resolver) to exist.
UEF-1's own vocabulary (`EventOrigin`, `ReturnUnit`, `MARKET_TIMEZONE`,
`canonicalize_fixed_clock_label`, `Checkpoint.horizon_set_id`) is reused
throughout, never duplicated.
"""

from __future__ import annotations

from enum import Enum


FORWARD_POLICY_SCHEMA_VERSION = "uef2a_forward_policy.v5"


class HorizonKind(str, Enum):
    """The shape of one checkpoint's target-timestamp rule. Unchanged from Fix1/Fix2 -- not flagged."""

    RELATIVE_SECONDS = "RELATIVE_SECONDS"
    SESSION_CLOSE = "SESSION_CLOSE"
    FORWARD_SESSION = "FORWARD_SESSION"
    FIXED_CLOCK_TARGET = "FIXED_CLOCK_TARGET"


class ForwardSessionResolverAuthority(str, Enum):
    """Which authority resolves "the Nth next session" for a FORWARD_SESSION horizon.

    ARTIFACT_AVAILABLE_SESSIONS is the ONLY member -- Opening Shadow's
    `delayed_path` builds its own `trading_calendar` from artifact-presence,
    never a market-calendar library (`opening_rank1_longitudinal/pipeline.py:96-105,203-204`).
    """

    ARTIFACT_AVAILABLE_SESSIONS = "ARTIFACT_AVAILABLE_SESSIONS"


class ObservationSelectionMode(str, Enum):
    """Which real market observation stands in for a checkpoint's target timestamp.

    `NEAREST` remains removed (zero legacy evidence, Fix1 M1).
    """

    EXACT = "EXACT"
    FIRST_AT_OR_AFTER = "FIRST_AT_OR_AFTER"
    LAST_AVAILABLE = "LAST_AVAILABLE"


class MissingResolutionPolicy(str, Enum):
    """What RULE a checkpoint follows once its own observation cannot be resolved yet.

    Distinct from `MissingObservationStatus` (the RESULT).
    """

    KEEP_PENDING = "KEEP_PENDING"
    EXPIRE_AFTER_TOLERANCE = "EXPIRE_AFTER_TOLERANCE"
    MARK_MISSING_IMMEDIATELY = "MARK_MISSING_IMMEDIATELY"
    USE_SESSION_CLOSE_FALLBACK = "USE_SESSION_CLOSE_FALLBACK"


class MissingObservationStatus(str, Enum):
    """The RESULT of applying a `MissingResolutionPolicy` -- never a return of 0.

    `INSUFFICIENT_FUTURE_SESSIONS` is NEW in the Reset: Opening Shadow's
    `delayed_path` real status string `"INSUFFICIENT_FUTURE_DAYS"`
    (`delayed_outcomes.py:126`) fires when a FORWARD_SESSION checkpoint's
    required intermediate sessions are not all present in the artifact-derived
    calendar -- genuinely distinct from every other missing reason (it is
    about session-COUNT sufficiency, not about a single bar's timing).
    """

    TARGET_NOT_REACHED = "TARGET_NOT_REACHED"
    NO_DATA = "NO_DATA"
    NO_OBSERVATION_WITHIN_TOLERANCE = "NO_OBSERVATION_WITHIN_TOLERANCE"
    SESSION_ENDED = "SESSION_ENDED"
    EVIDENCE_INVALID = "EVIDENCE_INVALID"
    INSUFFICIENT_FUTURE_SESSIONS = "INSUFFICIENT_FUTURE_SESSIONS"


class EvidenceVerificationState(str, Enum):
    """Input observation-quality gate for a collector-governed checkpoint.

    INPUT evidence quality, never a forward-OUTCOME status. Evidence: Q10
    Index's `_index_reaction` tri-state (`reaction_reader.py:310-337`).
    """

    ABSENT = "ABSENT"
    INVALID = "INVALID"
    VERIFIED = "VERIFIED"


class PriceCandidate(str, Enum):
    """ONE candidate price value. Real checkpoints consult these IN ORDER via `policy.PriceResolutionPolicy`.

    The Reset restores/extends this vocabulary after re-reading every real
    price/excursion resolution site in the inventory (never a single
    unordered value):

    - BAR_OPEN/BAR_CLOSE/BAR_HIGH/BAR_LOW: the candle's own OHLC fields.
    - QUOTE: a live snapshot field (Q10 Index collector's `"current"`), not
      a candle at all.
    - REFERENCE_PRICE: the episode's own already-established reference/
      baseline price -- the FALLBACK TARGET, never the first choice, in
      every real chain that uses it. Evidence: Q10 Semiconductor/Q12's
      shared engine, `close = _to_float(target_row.get("close"), base_price)
      or base_price` (`quant_shadow_forward_outcomes.py:337`) -- BAR_CLOSE
      tried first, `base_price` (the episode's own baseline) only if the
      candle's close is missing/zero; identically for the excursion scan,
      `high = ... or base_price` / `low = ... or base_price` (`:338-339`).
      Opening Shadow's own forward checkpoint: `close = _number(target.get
      ("close")) or entry_price` (`latent_forward.py:120`) -- same shape,
      BAR_CLOSE then the episode's own `entry_price`.
    - SOURCE_FIELD_PRICE/SOURCE_FIELD_CURRENT_PRICE/SOURCE_FIELD_CUR_PRICE:
      alternate raw field-name aliases for the same "current/last" price
      concept, found ONLY in Q9 Horizon/Exit's `_row_price(raw, "close",
      "price", "current_price", "cur_price")` (`strategy_horizon_feedback.py:914`)
      -- a 4-deep chain across differently-named upstream fields, not a
      fallback across different PRICING AUTHORITIES.
    - SOURCE_FIELD_HIGH_PRICE/SOURCE_FIELD_LOW_PRICE: the same alias
      pattern for the excursion fields in the SAME function --
      `_row_price(raw, "high", "high_price")` / `_row_price(raw, "low",
      "low_price")` (`:917-918`).
    - PRIMARY_PRICE_FALLBACK: a chain terminator meaning "reuse THIS row's
      own already-resolved primary (close-equivalent) price" -- evidence:
      the same Horizon/Exit function's excursion chains both end in `or
      close` (`:917-918`), falling back to the row's own resolved `close`
      value, never to the episode-wide reference price. Distinct from
      REFERENCE_PRICE (which is the EPISODE's price, not this row's own).
    - FIXED_OBSERVED_PRICE: the checkpoint's price is already resolved
      upstream and merely carried forward, no lookup at all (Q11's
      zero-offset ACTUAL_EXIT outcome checkpoint).
    """

    BAR_OPEN = "BAR_OPEN"
    BAR_CLOSE = "BAR_CLOSE"
    BAR_HIGH = "BAR_HIGH"
    BAR_LOW = "BAR_LOW"
    QUOTE = "QUOTE"
    REFERENCE_PRICE = "REFERENCE_PRICE"
    SOURCE_FIELD_PRICE = "SOURCE_FIELD_PRICE"
    SOURCE_FIELD_CURRENT_PRICE = "SOURCE_FIELD_CURRENT_PRICE"
    SOURCE_FIELD_CUR_PRICE = "SOURCE_FIELD_CUR_PRICE"
    SOURCE_FIELD_HIGH_PRICE = "SOURCE_FIELD_HIGH_PRICE"
    SOURCE_FIELD_LOW_PRICE = "SOURCE_FIELD_LOW_PRICE"
    PRIMARY_PRICE_FALLBACK = "PRIMARY_PRICE_FALLBACK"
    FIXED_OBSERVED_PRICE = "FIXED_OBSERVED_PRICE"


class ExcursionPriceField(str, Enum):
    """Which candle-level concept an MFE/MAE scan is fundamentally reading.

    `CLOSE` is RESTORED in the Reset -- re-reading Q10 Index's directional
    shadow calculator (`shadow_comparison.py::build_shadow_comparison`)
    shows its MFE/MAE are computed from a `close`-only price series
    (`prices = [float(row.get("close") or 0.0) for row in future ...]`,
    `signed_moves = [direction * (price/entry_price - 1)*100 for price in
    prices]`, `mfe_pct = max(signed_moves)`, `mae_pct = min(signed_moves)` --
    `shadow_comparison.py:96-99,114-115`) -- there is no separate high/low
    read anywhere in that function. This member was removed after Fix1
    (zero evidence at the time) and is restored now that real evidence
    exists -- the same "no evidence -> no active semantic" rule cuts both
    ways: real evidence found later must be represented, not left out for
    consistency with an earlier, incomplete search.
    """

    HIGH = "HIGH"
    LOW = "LOW"
    CLOSE = "CLOSE"


class MfeMaeWindowEnd(str, Enum):
    """Where an MFE/MAE scan window ends.

    `FORWARD_SESSION_BOUND` is NEW in the Boundary Closure: Opening
    Longitudinal's `delayed_path` MFE scan (`d{n}_max_high_net_pct`) is
    confined EXACTLY to `selected_rows = [row for day in selected_days for
    row in grouped.get(day) or []]` where `selected_days = future_days[:
    horizon]` (`delayed_outcomes.py:117-139`) -- the SAME bounded
    session-count window as the checkpoint's own `ForwardSessionSpec`, not
    an unbounded forward scan. A `HorizonSpec` using this window_end must
    be `kind=HorizonKind.FORWARD_SESSION` (enforced at construction) --
    the bound is always "this horizon's own `forward_session`", never a
    separately-specified count, since the real source never uses a
    different window for the excursion than for the checkpoint itself.
    Using `UNBOUNDED_FORWARD` here was a Boundary-Closure-audit finding
    (session target bounded, excursion incorrectly left unbounded).
    """

    TARGET_TIMESTAMP = "TARGET_TIMESTAMP"
    OWN_CHECKPOINT_OBSERVATION = "OWN_CHECKPOINT_OBSERVATION"
    UNBOUNDED_FORWARD = "UNBOUNDED_FORWARD"
    ACTUAL_EXIT = "ACTUAL_EXIT"
    FORWARD_SESSION_BOUND = "FORWARD_SESSION_BOUND"


class TradeDirection(str, Enum):
    """Long vs. short/inverse multiplier on the gross-return formula (episode/program-level)."""

    LONG = "LONG"
    SHORT = "SHORT"


class ReferenceResolutionKind(str, Enum):
    """HOW a policy's own reference/origin timestamp+price were established (Boundary Closure item 4/6).

    - EXTERNAL_EVENT_TIMESTAMP: the overwhelming majority -- the reference
      is simply the episode's own already-known origin event (a candidate/
      signal/entry/exit timestamp UEF-1 already models via `EventOrigin`),
      with a `PriceResolutionPolicy` chain to resolve its price (e.g.
      Opening Shadow's `open->close`).
    - PRE_RESOLVED_REFERENCE: the reference timestamp+price were already
      resolved by an UPSTREAM process before this forward calculator ever
      runs; the calculator (and UEF-2B) merely consumes the result, never
      re-derives it. `provenance` names which upstream algorithm produced
      it. Evidence: Q10 Index's `FIRST_PULLBACK_ENTRY`
      (`shadow_comparison.py::_first_pullback_entry`, `:43-64`) --
      Codex's final ownership ruling is **UPSTREAM_REFERENCE_RESOLUTION**:
      even though `_first_pullback_entry` physically reads
      `reaction.get("path")` from data produced inside this same evaluation
      package, the 0.5% `pullback_retrace_pct` threshold, the 60-minute
      lookback window, and the direction/`OVERREACTION`-gated retracement
      SCAN ALGORITHM ITSELF are a program-specific research technique, not
      a generic forward-measurement primitive -- "which package produced
      the input row" and "whose algorithm resolves the reference" are
      different questions, and boundary-ownership follows the latter.
      UEF-2B therefore never implements a retracement scan; it only needs
      to be able to consume an already-resolved reference, regardless of
      which upstream step produced it. This REPLACES the prior
      `RETRACEMENT_SCAN` member (removed) and its dedicated
      `retracement_lookback_seconds`/`retracement_threshold_fraction`
      fields (removed from `ReferenceResolutionPolicy`) -- those numeric
      parameters belong to the upstream algorithm's own semantic profile
      metadata, never to the generic engine's input contract.
    """

    EXTERNAL_EVENT_TIMESTAMP = "EXTERNAL_EVENT_TIMESTAMP"
    PRE_RESOLVED_REFERENCE = "PRE_RESOLVED_REFERENCE"


class DataCompletenessKind(str, Enum):
    """HOW an excursion scan's own input window is checked for gaps before it is trusted.

    `CONTIGUOUS_INTERVAL` is the ONE real member -- Q12 vnext's `outcomes.py::forward`
    computes `expected = (target - t) // 60 (+1 for EOD's appended target
    row)` and `complete = len(window) == expected` (`vnext/outcomes.py:23-24`),
    then gates MFE/MAE ENTIRELY on `complete` (`mfe_pct = ... if complete
    else None`, `:28-29`) -- a genuine gap-count check against a fixed
    interval (60-second minute bars), never a mere non-empty-window check.
    This is distinct from `MissingResolutionPolicy`/`MissingObservationStatus`
    (which govern the CHECKPOINT's own single target observation) --
    completeness governs the EXCURSION scan's intermediate bars.
    """

    CONTIGUOUS_INTERVAL = "CONTIGUOUS_INTERVAL"


class SourceResultCostSemantics(str, Enum):
    """Whether the LEGACY calculator's own result already contains a cost/slippage adjustment.

    Purely descriptive provenance -- UEF-2/UEF-2B compute gross movement
    ONLY (UEF-3 remains the sole cost/net authority); this field never
    triggers any cost computation, it only records what the SOURCE already
    did. Evidence: Q11's `simulate_probe_v0`/`_forward_returns` populate
    BOTH `gross_return_pct`/`return_pct` AND a `net_return_pct` (already
    `cost_pct`/`slippage_pct`-adjusted, `simulator.py:6-8,39-45`) in the
    SAME result dict -- `NET_OR_COST_INCLUDED` for that calculator, even
    though a gross figure is also present alongside it.
    """

    GROSS_ONLY = "GROSS_ONLY"
    NET_OR_COST_INCLUDED = "NET_OR_COST_INCLUDED"
    UNKNOWN = "UNKNOWN"


__all__ = [
    "FORWARD_POLICY_SCHEMA_VERSION",
    "HorizonKind",
    "ForwardSessionResolverAuthority",
    "ObservationSelectionMode",
    "MissingResolutionPolicy",
    "MissingObservationStatus",
    "EvidenceVerificationState",
    "PriceCandidate",
    "ExcursionPriceField",
    "MfeMaeWindowEnd",
    "TradeDirection",
    "ReferenceResolutionKind",
    "DataCompletenessKind",
    "SourceResultCostSemantics",
]
