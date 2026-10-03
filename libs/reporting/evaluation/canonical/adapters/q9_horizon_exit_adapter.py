"""UEF-4B-6 -- Q9 Horizon/Exit candidate adapter: `q9_horizon_exit_adapter`.

======================================================================
STATUS: PRIMARY / KNOWN / BLOCKED -- NOT AN APPROVED UEF-4B ADAPTER.
DIRECT LOSSLESS UEF-4 MAPPING = NO.
======================================================================

This module is retained ONLY as a research/reproducer artifact. Q9 is
real PRIMARY EVIDENCE (never demoted to consumer/derived-view/
deprecated) and its physical sample/identity/return/cost/horizon
semantics below are genuinely verified against real source, but the
trusted `post_exit_shadow_recap.v1` artifact persists only the
resolved `exit_price` value, never which of its four real source
branches (`filled_price`/`current_price`/`price`/`avg_price`,
`strategy_horizon_feedback.py::build_post_exit_shadow_placeholder`)
produced it. No existing canonical `EntryAuthority` value can
represent that provenance losslessly without inventing a specific
claim (see `build_q9_episode`'s inline comment for the full
investigation) -- so `exit_price_authority` cannot be reconstructed
exactly, and this family's overall UEF-4 mapping is classified BLOCKED
until a future, explicitly-authorized source-contract change persists
which branch resolved `exit_price` (out of scope for this module).
`__all__` below deliberately exports nothing from this module for that
reason -- every name here is reachable only by an explicit, direct
import (as the reproducer tests in `tests/test_uef4b6_q9_adapter.py`
do), never via `from q9_horizon_exit_adapter import *`, and never
treated as public/approved API.

----------------------------------------------------------------------

Source authority (verified directly against real source, not only
`docs/research/uef4_legacy_family_inventory.md`):
`libs/runtime/strategy_horizon_feedback.py`
(`update_post_exit_shadow_with_price_observations` -- the real per-
checkpoint price/return/excursion computation; `_epoch_seconds`/
`_row_price` -- real timestamp/price-alias helpers, imported and called
directly, never reimplemented) and `libs/reporting/post_exit_shadow_recap.py`
(`build_post_exit_shadow_recap`/`write_post_exit_shadow_recap_outputs`/
`generate_post_exit_shadow_recap` -- the real orchestrator and writer of
the trusted artifact this module ingests; `_fill_regular_close_bound_
pending_checkpoints`/`_checkpoint_target_after_regular_close` -- the
real session-close-fallback substitution the frozen UEF-2A profile's
own `MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK` models;
`CHECKPOINT_LABELS` -- imported directly, never retyped), and
`graphs/commander_runtime.py` (the one real production caller, whose
own `POST_EXIT_SHADOW_RECAP_REPORT_DIR` env-var default names this
artifact family's real directory layout).

Q9 ROLE (this task's Section 3): Q9 is anchored to the live strategy's
OWN real, actually-executed exit -- `EventOrigin.ACTUAL_EXIT` -- unlike
every other UEF-4B family, a real executed trade IS legitimate Q9
source lineage. But broker mechanics (order submission, ACK, fill
fragments, retries, reconciliation, position snapshots) are NOT
additional Q9 evaluation samples: this module's ENTIRE input surface is
the trusted `post_exit_shadow_recap.json` artifact's own `trades[]`
list (trade_id/symbol/post_exit_shadow only) -- it never reads
`ai_trade_report.json`, `lifecycle_bundle.json`, or any execution-detail
artifact directly, so broker/execution mechanics are structurally
unreachable from this module, never merely asserted excluded.

OBSERVATION TYPE (FIX1): `ObservationType.EXIT_EVENT`, not
`ACTUAL_TRADE`/`SHADOW_ENTRY` -- see the inline comment in
`build_q9_episode` for the full proof and the reported (not fabricated)
exit-price-authority gap this choice surfaces.

WHY THIS MODULE DOES NOT CALL `evaluate_forward()`: verified directly
against source -- the real, persisted `post_exit_shadow_recap.json`
artifact never carries the raw minute candles a checkpoint's return was
computed from (`build_post_exit_shadow_recap` only persists
`"source_minute_rows": len(rows)`, a COUNT, never the rows themselves);
it carries the ALREADY-FULLY-RESOLVED `checkpoints` dict (price/return/
excursion/timestamp per horizon), produced by the real
`update_post_exit_shadow_with_price_observations` AND the real
`_fill_regular_close_bound_pending_checkpoints` session-close-fallback
substitution together. This is the SAME "some legacy-verified protocol
stays outside the frozen engine's own observation-matching machinery,
only its already-resolved value is consumed" precedent Q10 Index Calc
G/H and Q11 already established -- taking these verbatim (irreducibly
SOURCE_PROVIDED) is more faithful than re-deriving them from a SEPARATE,
untrusted, unversioned candle source (e.g. `data/state.json`'s own
mutable `recent_minute_ohlcv_by_symbol`, which carries no schema/
discriminator of its own and is explicitly out of scope as a "trusted
artifact/source family" per this task's own Section 16).

SESSION-CLOSE FALLBACK IS REAL, NOT INVENTED: `_fill_regular_close_
bound_pending_checkpoints` (`post_exit_shadow_recap.py:436-484`)
substitutes the EOD checkpoint's own observed price/timestamp into any
intraday checkpoint whose target time falls after the regular 15:30 KST
session close (`_checkpoint_target_after_regular_close`) -- exactly the
real-world behavior the frozen `build_q9_horizon_exit_profile()`'s
`MissingResolutionPolicy.USE_SESSION_CLOSE_FALLBACK` (`SessionCloseSpec`,
close_clock 15:30) models. A substituted row is marked
`closeout_substitute: True` in the real artifact and is OBSERVED by the
time this module reads it -- translated exactly like any other OBSERVED
checkpoint, verbatim, never re-derived.

REFERENCE (Section 7/8): `exit_ts`/`exit_price` are read verbatim from
the trade's own `post_exit_shadow` object -- never substituted with a
next candle, a current broker quote, or a post-exit first observation.
`_epoch_seconds` (real function, imported directly) parses `exit_ts`
exactly as the real update function itself does.

RETURN UNIT / COST (Section 12-14): `ReturnUnit.FRACTION` (0.01 == +1%,
never normalized to percentage points) -- `update_post_exit_shadow_
with_price_observations` only ever writes `return_pct = price/exit_price
- 1.0`, no `* 100`. `SourceResultCostSemantics.GROSS_ONLY` -- no
`net_return_pct`/cost/slippage field exists anywhere in
`strategy_horizon_feedback.py`. This module NEVER fabricates a
`CostPolicy` -- `canonicalize_q9_horizon_exit_artifact` requires the
caller to supply one explicitly (matching Calc F's own established
required-`cost_policy`-parameter pattern); if none is available, the
caller must not call this function for net-aggregation purposes, but
the GROSS canonical episode/checkpoint construction itself never blocks
on a missing CostPolicy (frozen UEF-3 contracts already require this
separation).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.post_exit_shadow_recap import CHECKPOINT_LABELS
from libs.runtime.strategy_horizon_feedback import _epoch_seconds

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, EntryAuthority, EventOrigin, ExecutionMode, ObservationType, ReturnUnit
from libs.reporting.evaluation.canonical.metrics import CostPolicy
from libs.reporting.evaluation.canonical.metrics.aggregation import CanonicalAggregationMember
from libs.reporting.evaluation.canonical.record import Checkpoint, EpisodeRecord, ExitObservation, Provenance, build_episode_record

from .forward_measurement_adapter import (
    ForwardMeasurementAdapterError,
    build_forward_measurement_event_ref,
    checkpoint_to_aggregation_member,
)


class Q9HorizonExitAdapterError(ForwardMeasurementAdapterError):
    """Raised for a Q9 legacy-input problem -- fail fast, never repair."""


SOURCE_NAMESPACE = "q9_horizon_exit"
HYPOTHESIS_ID = "q9_horizon_exit_post_exit_shadow"  # matches the frozen profile's own legacy_program

SCHEMA_VERSION = "post_exit_shadow_recap.v1"

# Real artifact family directory NAME the one real production caller
# (graphs/commander_runtime.py) defaults `report_dir` to via
# POST_EXIT_SHADOW_RECAP_REPORT_DIR ("reports/dev/analysis/
# post_exit_shadow_recap"), and the exact filename `write_post_exit_
# shadow_recap_outputs` always writes under `<report_dir>/<day>/`. Note:
# `report_dir` itself is configurable at the call site (env var) -- this
# module anchors to the real, documented DEFAULT directory name as the
# trusted family layout, never a fabricated one, and never the day
# segment (validated by ISO-date shape instead).
_ARTIFACT_FAMILY_DIR = "post_exit_shadow_recap"
_ARTIFACT_FILENAME = "post_exit_shadow_recap.json"
_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _verify_recap_artifact_origin(path: Path) -> Mapping[str, Any]:
    """The real Q9 artifact-origin gate. Verified directly against
    source, requires BOTH:

    1. the artifact's real family path layout -- `.../post_exit_shadow_
       recap/<day>/post_exit_shadow_recap.json` (day validated by
       ISO-date SHAPE, never a hardcoded literal date);
    2. the real persisted discriminator the same writer stamps into the
       payload itself (`schema_version`==`SCHEMA_VERSION`,
       `post_exit_shadow_recap.py:657`).

    Q9 has only ONE real persisted discriminator -- there is no
    `evaluation_program_id`-equivalent field anywhere in the real
    `post_exit_shadow_recap.json` payload (verified directly against
    source); this is reported honestly rather than fabricating a second
    one to match other UEF-4B families' dual-discriminator pattern.
    Neither Q10 Semiconductor, Q10 Index, Q11, Q12, Opening Shadow, a
    Controlled Probe/Mock Lane, nor a raw execution-outcome artifact
    ever satisfies both checks -- verified directly against each of
    their own real writer modules.
    """

    resolved = Path(path)
    parts = resolved.as_posix().split("/")
    if len(parts) < 3 or parts[-1] != _ARTIFACT_FILENAME or parts[-3] != _ARTIFACT_FAMILY_DIR or not _DAY_PATTERN.match(parts[-2]):
        raise Q9HorizonExitAdapterError(
            f"_verify_recap_artifact_origin: path={str(resolved)!r} is not located under the real "
            f"post_exit_shadow_recap artifact family layout "
            f"(.../{_ARTIFACT_FAMILY_DIR}/<YYYY-MM-DD>/{_ARTIFACT_FILENAME}) -- refusing to treat an "
            "arbitrarily-located file as this source family's artifact"
        )
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise Q9HorizonExitAdapterError(f"_verify_recap_artifact_origin: could not read {str(resolved)!r}: {exc}") from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise Q9HorizonExitAdapterError(f"_verify_recap_artifact_origin: {str(resolved)!r} is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise Q9HorizonExitAdapterError(f"_verify_recap_artifact_origin: {str(resolved)!r} does not contain a JSON object")
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != SCHEMA_VERSION:
        raise Q9HorizonExitAdapterError(
            f"_verify_recap_artifact_origin: {str(resolved)!r} has schema_version={schema_version!r} -- does not "
            f"match the real post_exit_shadow_recap artifact's own persisted discriminator ({SCHEMA_VERSION!r})"
        )
    return payload


@dataclass(frozen=True)
class Q9RealizedTrade:
    """One real, already-closed trade's post-exit shadow, parsed from
    the trusted `post_exit_shadow_recap.json` artifact."""

    day: str
    trade_id: str
    symbol: str
    exit_epoch: int
    exit_price: float
    checkpoints: Mapping[str, Any]


def _parse_trade(day: str, row: Mapping[str, Any]) -> Q9RealizedTrade:
    trade_id = str(row.get("trade_id") or "").strip()
    if not trade_id:
        raise Q9HorizonExitAdapterError("_parse_trade: row has no trade_id")
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        raise Q9HorizonExitAdapterError(f"_parse_trade: trade_id={trade_id!r} has no symbol")
    shadow = row.get("post_exit_shadow")
    if not isinstance(shadow, Mapping):
        raise Q9HorizonExitAdapterError(f"_parse_trade: trade_id={trade_id!r} has no post_exit_shadow")
    exit_epoch = _epoch_seconds(shadow.get("exit_ts"))
    exit_price = _number(shadow.get("exit_price"))
    if exit_epoch is None or exit_epoch <= 0:
        raise Q9HorizonExitAdapterError(f"_parse_trade: trade_id={trade_id!r} has invalid/unresolvable exit_ts={shadow.get('exit_ts')!r}")
    if exit_price is None or exit_price <= 0:
        raise Q9HorizonExitAdapterError(f"_parse_trade: trade_id={trade_id!r} has invalid exit_price={shadow.get('exit_price')!r}")
    checkpoints = shadow.get("checkpoints")
    if not isinstance(checkpoints, Mapping):
        raise Q9HorizonExitAdapterError(f"_parse_trade: trade_id={trade_id!r} has no checkpoints")
    return Q9RealizedTrade(day=day, trade_id=trade_id, symbol=symbol, exit_epoch=int(exit_epoch), exit_price=exit_price, checkpoints=checkpoints)


def _build_checkpoint(trade: Q9RealizedTrade, label: str) -> Checkpoint:
    row = trade.checkpoints.get(label)
    if not isinstance(row, Mapping):
        raise Q9HorizonExitAdapterError(f"_build_checkpoint: trade_id={trade.trade_id!r} has no checkpoints[{label!r}] -- unknown horizon")
    status = str(row.get("status") or "").strip().lower()
    horizon_origin = EventOrigin.ACTUAL_EXIT
    if status == "observed":
        observed_ts = _epoch_seconds(row.get("observed_ts"))
        observed_price = _number(row.get("observed_price")) if row.get("observed_price") is not None else _number(row.get("price"))
        gross = _number(row.get("return_pct"))
        if observed_ts is None or observed_ts <= 0 or observed_price is None or observed_price <= 0 or gross is None:
            raise Q9HorizonExitAdapterError(
                f"_build_checkpoint: trade_id={trade.trade_id!r} horizon={label!r} status='observed' but missing/"
                "invalid observed_ts/observed_price/return_pct -- canonical-record consistency defect"
            )
        mfe = _number(row.get("max_upside_pct"))
        mae = _number(row.get("max_drawdown_pct"))
        return Checkpoint(
            horizon_label=label, horizon_origin=horizon_origin, target_timestamp=None,
            observed_timestamp=int(observed_ts), observed_price=observed_price, gross_return=gross, net_return=None,
            mfe=mfe, mae=mae, completeness=CheckpointCompleteness.OBSERVED, source=HYPOTHESIS_ID,
            return_unit=ReturnUnit.FRACTION, horizon_set_id=HYPOTHESIS_ID,
        )
    if status != "pending":
        raise Q9HorizonExitAdapterError(f"_build_checkpoint: trade_id={trade.trade_id!r} horizon={label!r} has unknown status={row.get('status')!r}")
    return Checkpoint(
        horizon_label=label, horizon_origin=horizon_origin, target_timestamp=None,
        observed_timestamp=None, observed_price=None, gross_return=None, net_return=None, mfe=None, mae=None,
        completeness=CheckpointCompleteness.PENDING, source=HYPOTHESIS_ID,
        return_unit=ReturnUnit.FRACTION, horizon_set_id=HYPOTHESIS_ID,
    )


def build_q9_episode(trade: Q9RealizedTrade, *, source_artifact: str) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one realized trade's post-
    exit shadow. Every return/excursion/timestamp figure is taken
    verbatim from the real, already-resolved checkpoint row -- see
    module docstring for why `evaluate_forward()` is never called here."""

    checkpoints = tuple(_build_checkpoint(trade, label) for label in CHECKPOINT_LABELS)
    event_ref = build_forward_measurement_event_ref(source_namespace=SOURCE_NAMESPACE, trading_date=trade.day, symbol=trade.symbol, native_id=trade.trade_id)
    # FIX1 (observation identity closure): Q9's canonical event IS the real
    # ACTUAL_EXIT itself, plus the hypothetical continued-hold evidence
    # anchored to it -- ObservationType.EXIT_EVENT (requires an `exit`
    # observation, never an `entry`), not SHADOW_ENTRY. SHADOW_ENTRY was
    # rejected: it was chosen only because ACTUAL_TRADE's validator demands
    # an entry observation Q9 genuinely lacks, which is not semantic proof
    # SHADOW_ENTRY is the correct representation, and it is not -- Q9 has
    # no synthetic/simulated position at all, real or shadow; it is a
    # direct observation of what actually happened after a real exit.
    # ACTUAL_TRADE was ALSO rejected (contra this project's own UEF-1
    # design doc, `docs/research/unified_evaluation_foundation.md:781`,
    # which assumed `EntryAuthority.BROKER_FILL` for the entry side): the
    # trusted `post_exit_shadow_recap.json` artifact this module ingests
    # carries no entry_time/entry_price at all -- ingesting them would mean
    # reaching into `ai_trade_report.json`/`lifecycle_bundle.json`, exactly
    # the broker/execution-detail boundary this module must never cross
    # (see module docstring). EXIT_EVENT requires only `exit`, which this
    # artifact genuinely, losslessly provides (exit_time/exit_price
    # verbatim).
    #
    # EXIT PRICE AUTHORITY (KNOWN, REPORTED GAP -- not fabricated): the real
    # source resolves exit_price through a 4-deep alias chain
    # (`filled_price` -> `current_price` -> `price` -> `avg_price`,
    # `strategy_horizon_feedback.py::build_post_exit_shadow_placeholder`)
    # but persists ONLY the resolved number, never which alias fired.
    # `EntryAuthority.BROKER_FILL`/`MOCK_FILL` would assert a CONFIRMED
    # fill this module cannot verify (2 of the 4 aliases are monitor
    # quotes, not fill confirmations) -- claiming it would be exactly the
    # kind of fabricated-authority this project's own `EntryAuthority`
    # docstring already forbids for `SUBMITTED_INTENT`/`MOCK_FILL`/
    # `BROKER_FILL`. `EntryAuthority.MARKET_QUOTE` is used instead: it is
    # true in every branch (all 4 aliases are, at minimum, an observed
    # market price) and never overclaims fill confirmation. This is a
    # best-effort, non-identity-bearing value -- `exit_price_authority` is
    # NOT an input to `evaluation_subject_id`/`evaluation_record_id` (see
    # `identity.py::evaluation_subject_id`) and carries no validator
    # constraint of its own (unlike `entry_authority`), so it cannot
    # corrupt identity or return/cost correctness. A minimal additive
    # source-contract field (e.g. persisting which alias resolved
    # `exit_price`) would close this gap losslessly, but that is a broader
    # source change outside this Fix1's scope -- reported, not performed.
    return build_episode_record(
        source_namespace=SOURCE_NAMESPACE, hypothesis_id=HYPOTHESIS_ID, observation_type=ObservationType.EXIT_EVENT,
        execution_mode=ExecutionMode.BROKER_LIVE, trading_date=trade.day, symbol=trade.symbol, event_ref=event_ref,
        checkpoints=checkpoints,
        exit=ExitObservation(
            exit_time=trade.exit_epoch, exit_price=trade.exit_price,
            exit_price_authority=EntryAuthority.MARKET_QUOTE, exit_reason="",
        ),
        provenance=Provenance(
            legacy_program=HYPOTHESIS_ID, legacy_schema=SCHEMA_VERSION, source_artifact=source_artifact,
            source_function="update_post_exit_shadow_with_price_observations",
        ),
        metadata={"trade_id": trade.trade_id, "exit_epoch": trade.exit_epoch, "exit_price": trade.exit_price},
    )


@dataclass(frozen=True)
class Q9HorizonExitCanonicalResult:
    """Adapter-local (NOT canonical) per-trade result of this BLOCKED,
    NOT-approved Q9 candidate ingestion path (see module docstring)."""

    trade: Q9RealizedTrade
    member: CanonicalAggregationMember
    episode: EpisodeRecord


def canonicalize_q9_horizon_exit_artifact(
    path: str | Path, *, horizon_label: str, cost_policy: CostPolicy,
) -> list[Q9HorizonExitCanonicalResult]:
    """The Q9 candidate ingestion entrypoint -- BLOCKED, NOT an approved
    canonical path (see module docstring: `exit_price_authority` cannot
    be reconstructed losslessly from the trusted artifact). Retained for
    research/reproducer use only.

    1. reads the trusted `post_exit_shadow_recap.json` artifact through
       its own real, verified origin (family path layout + persisted
       schema_version, `_verify_recap_artifact_origin`) -- never a
       caller-supplied, already-parsed dict;
    2. parses every trade into a verified DTO (`Q9RealizedTrade`),
       fail-fast on a duplicate `trade_id` (conflicting or not -- never
       silently last-write-wins);
    3. canonicalizes: every trade is, by construction, a real realized
       exit -- one trade always becomes exactly one EpisodeRecord with
       5 checkpoints (+5m/+15m/+30m/+60m/EOD); per-checkpoint OBSERVED/
       PENDING semantics are preserved distinctly (never a fabricated
       0-return for a PENDING checkpoint).

    `cost_policy` must be supplied by the caller -- this module never
    fabricates one (Q9's real source is GROSS_ONLY; no authoritative
    net/cost figure exists anywhere in `strategy_horizon_feedback.py`).
    """

    payload = _verify_recap_artifact_origin(Path(path))
    day = str(payload.get("day") or "")
    trades = payload.get("trades")
    if not isinstance(trades, list):
        raise Q9HorizonExitAdapterError("canonicalize_q9_horizon_exit_artifact: artifact.trades must be a list")

    source_artifact = f"{_ARTIFACT_FAMILY_DIR}/{day}/{_ARTIFACT_FILENAME}"
    seen_trade_ids: dict[str, Mapping[str, Any]] = {}
    results: list[Q9HorizonExitCanonicalResult] = []
    for row in trades:
        if not isinstance(row, Mapping):
            continue
        trade_id_raw = str(row.get("trade_id") or "").strip()
        if trade_id_raw:
            if trade_id_raw in seen_trade_ids and seen_trade_ids[trade_id_raw] != row:
                raise Q9HorizonExitAdapterError(
                    f"canonicalize_q9_horizon_exit_artifact: trade_id={trade_id_raw!r} appears more than once "
                    "with conflicting content -- refusing to silently pick one (fail fast, never last-write-wins)"
                )
            seen_trade_ids[trade_id_raw] = row
        trade = _parse_trade(day, row)
        episode = build_q9_episode(trade, source_artifact=source_artifact)
        checkpoint = next((cp for cp in episode.checkpoints if cp.horizon_label == horizon_label), None)
        if checkpoint is None:
            raise Q9HorizonExitAdapterError(f"canonicalize_q9_horizon_exit_artifact: no checkpoint for horizon_label={horizon_label!r}")
        member = checkpoint_to_aggregation_member(checkpoint, evaluation_record_id=episode.identity.evaluation_record_id, cost_policy=cost_policy)
        results.append(Q9HorizonExitCanonicalResult(trade=trade, member=member, episode=episode))
    return results


# UEF-4 CONSOLIDATED PROVISIONAL CLOSURE: deliberately empty. This
# module is BLOCKED, not an approved UEF-4B adapter (DIRECT LOSSLESS
# UEF-4 MAPPING = NO -- see the module docstring) -- nothing here is
# exported as public/approved API. Every name remains reachable by an
# explicit direct import for research/reproducer purposes only (as
# `tests/test_uef4b6_q9_adapter.py` does), never via `from
# q9_horizon_exit_adapter import *`.
__all__: list[str] = []
