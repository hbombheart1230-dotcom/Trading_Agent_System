"""UEF-4B-5 -- Q11 Opportunity Engine canonical adapter: `virtual_probe_adapter`.

Source authority (verified directly against real source, not only
`docs/research/uef4_legacy_family_inventory.md`):
`libs/research/opportunity_engine/simulator.py` (`simulate_probe_v0` --
one closed virtual position = one `trades[]` entry; `_forward_returns`
-- the 4 SIGNAL-anchored forward checkpoints + EOD),
`libs/research/opportunity_engine/engine.py` (`build_signal_timeline`
-- Q11's OWN self-generated `signal_id`, never any other family's
decision id), `libs/research/opportunity_engine/pipeline.py`
(`build_opportunity_engine_artifacts` -- the real writer of the trusted
artifact this module ingests), `libs/research/opportunity_engine/
contracts.py` (`PROGRAM_ID`/`TRADES_SCHEMA`/`DEFAULT_SYMBOLS`/
`PROHIBITED_RUNTIME_DEPENDENCIES` -- imported directly, never retyped).

Q11 ROLE / VIRTUAL / NEGATIVE-CONTROL SEMANTICS (this task's Section 7,
resolved from source, never inferred from the "virtual"/"negative
control" labels alone): Q11 is a self-contained RESEARCH PROBE that
generates its OWN candidate stream directly from real minute candles +
real macro-market snapshots (`build_signal_timeline`'s own
`signal_id = f"OE_{day}_{symbol}_{epoch}"`, computed purely from candle
data + Q11's own `score_opportunity` rule -- NEVER a reference to a
Scanner/Commander/Strategist decision id, and never an import from
either: `contracts.py::PROHIBITED_RUNTIME_DEPENDENCIES` explicitly lists
`graphs.nodes`, `libs.runtime.commander`, `libs.runtime.execution`,
`libs.runtime.quant.shadow_candidates`, and even
`libs.reporting.evaluation` itself, as forbidden imports for the
opportunity_engine package -- a REAL, deliberate architectural isolation
this adapter's own existence does not violate, since it imports FROM
opportunity_engine, never the reverse). "Virtual" means the resulting
position was NEVER submitted to a broker -- every trade the real
simulator emits carries `order_execution_allowed: False` and
`behavior_effect: "shadow_only"` verbatim in the source data itself.
"Negative control" means this probe encodes ONE fixed, always-on
research entry/exit rule (`strategy_id="probe_v0"`) evaluated against
real market data as a baseline research arm -- distinct from, and never
compared against within this adapter, the live strategy's own real
decisions (that comparison is explicitly a downstream Q100/research
concern, never this adapter's job, per this task's Section 10).

REAL MARKET OBSERVATION: YES (real minute OHLCV candles, real macro
snapshots). REAL EXECUTION: NO. SYNTHETIC EVALUATION: the ENTRY TRIGGER
is Q11's own synthetic, self-generated scoring rule; the underlying
PRICE DATA and forward outcome are real market prices, never simulated.

PHYSICAL EVENT MODEL (Section 8): because Q11 generates its own entry
events from its own rule rather than reinterpreting an event another
family already canonicalizes, there is no cross-family physical/
counterfactual identity split to resolve here (unlike Q10 Index Calc H,
which shares physical identity with Calc F/G) -- EACH closed virtual
position is its OWN, sole, primary physical event, exactly like every
other single-population family in this project (Q9, Opening 1A). For
one representative trade: PHYSICAL EVENT COUNT=1, EPISODE COUNT=1,
COUNTERFACTUAL/HYPOTHESIS COUNT=1 (Q11 encodes exactly one fixed
strategy variant, `probe_v0` -- no multiple entry-policy dimension like
Q10 Index Calc H's 5 `SHADOW_ENTRY_POLICIES`), CHECKPOINT COUNT=6 (+5m,
+15m, +30m, +60m, EOD -- all `SIGNAL`-anchored, from `forward_returns`;
EXIT -- `ACTUAL_EXIT`-anchored, from the trade's own top-level fields,
structurally separate from `forward_returns`, never nested inside it).

WHY `evaluate_forward()` IS NOT CALLED HERE: exactly like Q10 Index Calc
G/H (see `q10_index_reaction_adapter.py`/`q10_index_directional_shadow_
adapter.py`'s own module docstrings), every return/excursion figure Q11
needs is ALREADY fully resolved in the real, persisted
`opportunity_engine_virtual_trades.json` artifact -- `entry_price`
(BAR_CLOSE -> SOURCE_FIELD_PRICE, `simulator.py:125`), each forward
horizon's `return_pct`/`net_return_pct`/`mfe_pct`/`mae_pct`/
`observed_epoch` (`_forward_returns`, `simulator.py:11-77`), and the
EXIT checkpoint's own `exit_epoch`/`exit_price`/`gross_return_pct`/
`net_return_pct`/`mfe_pct`/`mae_pct` (`simulator.py:163-192`). Taking
these verbatim -- irreducibly SOURCE_PROVIDED, `NET_OR_COST_INCLUDED` --
matches the frozen `build_q11_opportunity_engine_profile()`'s own
classification exactly; `CostPolicy` must never be reapplied.

EXECUTION BOUNDARY: this module imports nothing from
`opening_rank1_controlled_probe.py`, `controlled_mock_lanes/`, or any
broker/executor/order module. Every real Q11 trade carries
`order_execution_allowed: False` verbatim -- this adapter fails fast if
that field is ever missing or `True` on an ingested trade, rather than
silently trusting artifact origin alone to guarantee it.

FIX1 SOURCE-CONTRACT REPAIR (`opportunity_engine_virtual_trades.v1` ->
`.v2`): independent audit found the +5m/+15m/+30m/+60m/EOD checkpoints
are genuinely `CheckpointMetricKind.PRICE_BASED` (each is anchored to
one real, actually-observed candle close, `simulator.py:34,44-46`,
`:59-60`) -- using `AGGREGATE_ONLY` to bypass the frozen contract's own
`observed_price` requirement was invalid, since these outcomes ARE
price-anchored, not "not anchored to one observed price" (the
`AGGREGATE_ONLY` docstring's own stated use case). The real defect was
upstream: `_forward_returns()` (`simulator.py`) computed every return/
MFE/MAE from a specific candle `close` but never persisted that price
in its own output. Repaired ADDITIVELY (`simulator.py` now persists
`"observed_price": close` alongside the unchanged return/MFE/MAE/
observed_epoch fields for every OBSERVED horizon; PENDING horizons still
omit it entirely) -- no selection/rounding/fallback semantics changed,
confirmed by the unchanged `OUTCOME ORACLE` test. `contracts.py::
TRADES_SCHEMA` bumped `.v1` -> `.v2` to mark this real schema-shape
change; `TRADES_SCHEMA_LEGACY_V1` names the now-superseded literal. This
module's own trusted-ingestion gate (`_verify_trades_artifact_origin`)
explicitly detects an authentic v1 artifact (real path, real
`evaluation_program_id`, `schema_version==TRADES_SCHEMA_LEGACY_V1`) and
blocks it with a specific reason (`observed_price` never persisted for
a price-based checkpoint) -- never a generic "unknown schema" rejection,
and never silently accepted. v1 artifacts remain real, KNOWN primary
evidence; DIRECT LOSSLESS UEF-4B canonicalization from v1 is BLOCKED,
never approximated. Recovering v1's own historical evidence (rerunning
real market inputs through the repaired v2 source contract) is an
explicit UEF-5 Historical Recompute concern, never this adapter's job
-- this module never rewrites, backfills, or mutates a v1 artifact.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from libs.research.opportunity_engine.contracts import PROGRAM_ID, TRADES_SCHEMA, TRADES_SCHEMA_LEGACY_V1

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, CheckpointMetricKind, EventOrigin, ExecutionMode, ObservationType, ReturnUnit
from libs.reporting.evaluation.canonical.forward import SourceResultCostSemantics
from libs.reporting.evaluation.canonical.identity import build_event_ref
from libs.reporting.evaluation.canonical.metrics.aggregation import CanonicalAggregationMember, SampleMemberState
from libs.reporting.evaluation.canonical.record import Checkpoint, EpisodeRecord, EventRef, Provenance, build_episode_record


class VirtualProbeAdapterError(ValueError):
    """Raised for a Q11 legacy-input problem -- fail fast, never repair."""


SOURCE_NAMESPACE = "q11_opportunity_engine"
HYPOTHESIS_ID = "q11_opportunity_engine"  # matches the frozen profile's own legacy_program

# Real, repo-relative artifact family path layout `build_opportunity_
# engine_artifacts` actually writes to (`pipeline.py:103-105`): a
# day-variable directory, never a hardcoded date.
_OPPORTUNITY_ENGINE_SHADOW_DIR = "opportunity_engine_shadow"
_TRADES_ARTIFACT_FILENAME = "opportunity_engine_virtual_trades.json"
_DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_FORWARD_HORIZON_LABELS = ("+5m", "+15m", "+30m", "+60m")
_ALL_HORIZON_LABELS = _FORWARD_HORIZON_LABELS + ("EOD", "EXIT")
_FORWARD_HORIZON_SECONDS = {"+5m": 300, "+15m": 900, "+30m": 1800, "+60m": 3600}


def _number(value: Any) -> float | None:
    try:
        return None if value in (None, "") else float(value)
    except (TypeError, ValueError):
        return None


def _verify_trades_artifact_origin(path: Path) -> Mapping[str, Any]:
    """The real Q11 artifact-origin gate. Verified directly against
    source, requires BOTH:

    1. the artifact's real, repo-relative FAMILY PATH LAYOUT -- the exact
       path `build_opportunity_engine_artifacts` actually writes to
       (`.../opportunity_engine_shadow/<day>/opportunity_engine_virtual_
       trades.json`, `pipeline.py:103-105`), the `<day>` segment
       validated by ISO-date SHAPE, never a hardcoded literal date;
    2. both real persisted discriminators the same writer stamps into
       the payload itself (`schema_version`==`TRADES_SCHEMA` AND
       `evaluation_program_id`==`PROGRAM_ID`, both imported verbatim from
       `opportunity_engine/contracts.py`, `pipeline.py:149-168`).

    Mirrors the Q10 Index dual-discriminator trusted-ingestion pattern
    exactly. Neither Q10 Semiconductor, Q10 Index, Q12, Opening Shadow,
    a Controlled Probe/Mock Lane, nor a Scanner/execution artifact ever
    satisfies both checks -- verified directly against each of their own
    real writer modules.
    """

    resolved = Path(path)
    parts = resolved.as_posix().split("/")
    if len(parts) < 3 or parts[-1] != _TRADES_ARTIFACT_FILENAME or parts[-3] != _OPPORTUNITY_ENGINE_SHADOW_DIR or not _DAY_PATTERN.match(parts[-2]):
        raise VirtualProbeAdapterError(
            f"_verify_trades_artifact_origin: path={str(resolved)!r} is not located under the real "
            f"opportunity_engine_virtual_trades artifact family layout "
            f"(.../{_OPPORTUNITY_ENGINE_SHADOW_DIR}/<YYYY-MM-DD>/{_TRADES_ARTIFACT_FILENAME}) -- refusing to treat "
            "an arbitrarily-located file as this source family's artifact"
        )
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError as exc:
        raise VirtualProbeAdapterError(f"_verify_trades_artifact_origin: could not read {str(resolved)!r}: {exc}") from exc
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise VirtualProbeAdapterError(f"_verify_trades_artifact_origin: {str(resolved)!r} is not valid JSON: {exc}") from exc
    if not isinstance(payload, Mapping):
        raise VirtualProbeAdapterError(f"_verify_trades_artifact_origin: {str(resolved)!r} does not contain a JSON object")
    schema_version = str(payload.get("schema_version") or "")
    program_id = str(payload.get("evaluation_program_id") or "")
    if program_id == PROGRAM_ID and schema_version == TRADES_SCHEMA_LEGACY_V1:
        # FIX1: an AUTHENTIC Q11 artifact, real family path, real program
        # id -- but the legacy v1 schema never persists each price-based
        # checkpoint's own observed_price (only the already-derived
        # return/MFE/MAE percentages). This is real, KNOWN primary
        # evidence, explicitly BLOCKED from direct lossless
        # canonicalization -- never approximated, never silently
        # accepted under a schema-mismatch label.
        raise VirtualProbeAdapterError(
            f"_verify_trades_artifact_origin: {str(resolved)!r} is an authentic legacy "
            f"{TRADES_SCHEMA_LEGACY_V1!r} Q11 artifact -- real primary evidence, but this schema version never "
            "persists each OBSERVED forward/EOD checkpoint's own observed_price (only the already-derived "
            "return/MFE/MAE percentages), so a lossless PRICE_BASED canonical checkpoint cannot be built from it. "
            f"DIRECT LOSSLESS UEF-4B MAPPING: BLOCKED for this version -- only {TRADES_SCHEMA!r} (or a later "
            "schema that also persists observed_price) is approved for canonicalization; historical recovery of "
            "v1 evidence is a UEF-5 Historical Recompute concern, never this adapter's job"
        )
    if schema_version != TRADES_SCHEMA or program_id != PROGRAM_ID:
        raise VirtualProbeAdapterError(
            f"_verify_trades_artifact_origin: {str(resolved)!r} has schema_version={schema_version!r} "
            f"evaluation_program_id={program_id!r} -- does not match the real opportunity_engine_virtual_trades "
            f"artifact's own persisted discriminators ({TRADES_SCHEMA!r}, {PROGRAM_ID!r})"
        )
    return payload


@dataclass(frozen=True)
class Q11VirtualProbeTrade:
    """One real, already-closed `simulate_probe_v0` trade, parsed from
    the trusted `opportunity_engine_virtual_trades.json` artifact."""

    day: str
    trade_id: str
    symbol: str
    entry_epoch: int
    entry_price: float
    exit_epoch: int
    exit_price: float
    exit_reason: str
    gross_return_pct: float
    net_return_pct: float
    mfe_pct: float
    mae_pct: float
    forward_returns: Mapping[str, Any]


def _parse_trade(day: str, row: Mapping[str, Any]) -> Q11VirtualProbeTrade:
    trade_id = str(row.get("trade_id") or "").strip()
    if not trade_id:
        raise VirtualProbeAdapterError("_parse_trade: row has no trade_id")
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        raise VirtualProbeAdapterError(f"_parse_trade: trade_id={trade_id!r} has no symbol")
    if bool(row.get("order_execution_allowed")):
        raise VirtualProbeAdapterError(
            f"_parse_trade: trade_id={trade_id!r} has order_execution_allowed=True -- a Q11 virtual probe must "
            "never represent real, broker-executable evidence; refusing to canonicalize"
        )
    if "order_execution_allowed" not in row:
        raise VirtualProbeAdapterError(
            f"_parse_trade: trade_id={trade_id!r} is missing order_execution_allowed -- cannot verify this is "
            "virtual, never real execution evidence; refusing to canonicalize rather than assume"
        )
    entry_epoch = row.get("entry_epoch")
    entry_price = _number(row.get("entry_price"))
    if entry_epoch is None or int(entry_epoch) <= 0:
        raise VirtualProbeAdapterError(f"_parse_trade: trade_id={trade_id!r} has invalid entry_epoch={entry_epoch!r}")
    if entry_price is None or not math.isfinite(entry_price) or entry_price <= 0:
        raise VirtualProbeAdapterError(f"_parse_trade: trade_id={trade_id!r} has invalid entry_price={entry_price!r}")
    exit_epoch = row.get("exit_epoch")
    exit_price = _number(row.get("exit_price"))
    if exit_epoch is None or int(exit_epoch) <= 0:
        raise VirtualProbeAdapterError(f"_parse_trade: trade_id={trade_id!r} has invalid exit_epoch={exit_epoch!r}")
    if exit_price is None or not math.isfinite(exit_price) or exit_price <= 0:
        raise VirtualProbeAdapterError(f"_parse_trade: trade_id={trade_id!r} has invalid exit_price={exit_price!r}")
    gross = _number(row.get("gross_return_pct"))
    net = _number(row.get("net_return_pct"))
    mfe = _number(row.get("mfe_pct"))
    mae = _number(row.get("mae_pct"))
    if gross is None or net is None or mfe is None or mae is None:
        raise VirtualProbeAdapterError(
            f"_parse_trade: trade_id={trade_id!r} is missing gross_return_pct/net_return_pct/mfe_pct/mae_pct -- "
            "a closed Q11 trade always carries these in the real source; canonical-record consistency defect"
        )
    if not (math.isfinite(gross) and math.isfinite(net) and math.isfinite(mfe) and math.isfinite(mae)):
        raise VirtualProbeAdapterError(f"_parse_trade: trade_id={trade_id!r} has a non-finite (NaN/inf) gross/net/mfe/mae value")
    forward_returns = row.get("forward_returns")
    if not isinstance(forward_returns, Mapping):
        raise VirtualProbeAdapterError(f"_parse_trade: trade_id={trade_id!r} has no forward_returns")
    return Q11VirtualProbeTrade(
        day=day, trade_id=trade_id, symbol=symbol,
        entry_epoch=int(entry_epoch), entry_price=entry_price,
        exit_epoch=int(exit_epoch), exit_price=exit_price, exit_reason=str(row.get("exit_reason") or ""),
        gross_return_pct=gross, net_return_pct=net, mfe_pct=mfe, mae_pct=mae,
        forward_returns=forward_returns,
    )


def _forward_checkpoint(trade: Q11VirtualProbeTrade, label: str) -> Checkpoint:
    row = trade.forward_returns.get(label)
    if not isinstance(row, Mapping):
        raise VirtualProbeAdapterError(f"_forward_checkpoint: trade_id={trade.trade_id!r} has no forward_returns[{label!r}] -- unknown horizon")
    status = str(row.get("status") or "")
    target_timestamp = trade.entry_epoch + _FORWARD_HORIZON_SECONDS[label]
    if status == "observed":
        observed_epoch = row.get("observed_epoch")
        gross = _number(row.get("return_pct"))
        net = _number(row.get("net_return_pct"))
        observed_price = _number(row.get("observed_price"))
        if observed_epoch is None or int(observed_epoch) <= 0 or gross is None or net is None:
            raise VirtualProbeAdapterError(
                f"_forward_checkpoint: trade_id={trade.trade_id!r} horizon={label!r} status='observed' but "
                "missing observed_epoch/return_pct/net_return_pct -- canonical-record consistency defect"
            )
        if observed_price is None or not math.isfinite(observed_price) or observed_price <= 0:
            # FIX1: this checkpoint IS anchored to one real, actually-
            # observed market price (the exact candle close
            # `_forward_returns()` computed return/MFE/MAE from,
            # simulator.py:34,44-46) -- a v2-schema artifact must always
            # carry it. Never fabricated backwards from the return, and
            # never silently downgraded to AGGREGATE_ONLY.
            raise VirtualProbeAdapterError(
                f"_forward_checkpoint: trade_id={trade.trade_id!r} horizon={label!r} status='observed' but "
                f"observed_price={row.get('observed_price')!r} is missing/invalid -- a {TRADES_SCHEMA!r} artifact "
                "must persist the exact source price this checkpoint's return was computed from"
            )
        mfe = _number(row.get("mfe_pct"))
        mae = _number(row.get("mae_pct"))
        return Checkpoint(
            horizon_label=label, horizon_origin=EventOrigin.SIGNAL, target_timestamp=target_timestamp,
            observed_timestamp=int(observed_epoch), observed_price=observed_price, gross_return=gross, net_return=net,
            mfe=mfe, mae=mae, completeness=CheckpointCompleteness.OBSERVED, source=HYPOTHESIS_ID,
            return_unit=ReturnUnit.PERCENTAGE_POINTS, horizon_set_id=HYPOTHESIS_ID,
            metric_kind=CheckpointMetricKind.PRICE_BASED,
        )
    if status != "pending":
        raise VirtualProbeAdapterError(f"_forward_checkpoint: trade_id={trade.trade_id!r} horizon={label!r} has unknown status={status!r}")
    return Checkpoint(
        horizon_label=label, horizon_origin=EventOrigin.SIGNAL, target_timestamp=target_timestamp,
        observed_timestamp=None, observed_price=None, gross_return=None, net_return=None, mfe=None, mae=None,
        completeness=CheckpointCompleteness.PENDING, source=HYPOTHESIS_ID,
        return_unit=ReturnUnit.PERCENTAGE_POINTS, horizon_set_id=HYPOTHESIS_ID,
    )


def _eod_checkpoint(trade: Q11VirtualProbeTrade) -> Checkpoint:
    row = trade.forward_returns.get("EOD")
    if not isinstance(row, Mapping):
        raise VirtualProbeAdapterError(f"_eod_checkpoint: trade_id={trade.trade_id!r} has no forward_returns['EOD']")
    status = str(row.get("status") or "")
    if status == "observed":
        observed_epoch = row.get("observed_epoch")
        gross = _number(row.get("return_pct"))
        net = _number(row.get("net_return_pct"))
        observed_price = _number(row.get("observed_price"))
        if observed_epoch is None or int(observed_epoch) <= 0 or gross is None or net is None:
            raise VirtualProbeAdapterError(
                f"_eod_checkpoint: trade_id={trade.trade_id!r} status='observed' but missing observed_epoch/"
                "return_pct/net_return_pct -- canonical-record consistency defect"
            )
        if observed_price is None or not math.isfinite(observed_price) or observed_price <= 0:
            # FIX1: same requirement as the forward horizons -- see there.
            raise VirtualProbeAdapterError(
                f"_eod_checkpoint: trade_id={trade.trade_id!r} status='observed' but "
                f"observed_price={row.get('observed_price')!r} is missing/invalid -- a {TRADES_SCHEMA!r} artifact "
                "must persist the exact source price this checkpoint's return was computed from"
            )
        # EOD genuinely has NO excursion at all by real source design
        # (simulator.py:56-77 -- no mfe_pct/mae_pct key exists), never
        # conflated with a resolvable-but-absent observation.
        return Checkpoint(
            horizon_label="EOD", horizon_origin=EventOrigin.SIGNAL, target_timestamp=None,
            observed_timestamp=int(observed_epoch), observed_price=observed_price, gross_return=gross, net_return=net,
            mfe=None, mae=None, completeness=CheckpointCompleteness.OBSERVED, source=HYPOTHESIS_ID,
            return_unit=ReturnUnit.PERCENTAGE_POINTS, horizon_set_id=HYPOTHESIS_ID,
            metric_kind=CheckpointMetricKind.PRICE_BASED,
        )
    if status != "pending":
        raise VirtualProbeAdapterError(f"_eod_checkpoint: trade_id={trade.trade_id!r} EOD has unknown status={status!r}")
    return Checkpoint(
        horizon_label="EOD", horizon_origin=EventOrigin.SIGNAL, target_timestamp=None,
        observed_timestamp=None, observed_price=None, gross_return=None, net_return=None, mfe=None, mae=None,
        completeness=CheckpointCompleteness.PENDING, source=HYPOTHESIS_ID,
        return_unit=ReturnUnit.PERCENTAGE_POINTS, horizon_set_id=HYPOTHESIS_ID,
    )


def _exit_checkpoint(trade: Q11VirtualProbeTrade) -> Checkpoint:
    # Every trade in the real trades[] list is, by construction, already
    # fully closed (simulator.py only appends after stop_hit/signal_faded/
    # timeout resolves) -- EXIT is therefore always OBSERVED for a
    # persisted trade; there is no PENDING/MISSING EXIT state at this
    # layer (an unclosed position simply never becomes a trades[] member
    # at all -- see module docstring, "no separate EXCLUDED/PENDING
    # trade-level state exists in this source").
    return Checkpoint(
        horizon_label="EXIT", horizon_origin=EventOrigin.ACTUAL_EXIT, target_timestamp=trade.exit_epoch,
        observed_timestamp=trade.exit_epoch, observed_price=trade.exit_price,
        gross_return=trade.gross_return_pct, net_return=trade.net_return_pct,
        mfe=trade.mfe_pct, mae=trade.mae_pct, completeness=CheckpointCompleteness.OBSERVED,
        source=HYPOTHESIS_ID, return_unit=ReturnUnit.PERCENTAGE_POINTS, horizon_set_id=HYPOTHESIS_ID,
    )


def _build_probe_event_ref(trade: Q11VirtualProbeTrade) -> EventRef:
    # trade_id is the real, deterministic, already-persisted identifier
    # the source itself computes (f"OE_TRD_{symbol}_{entry_epoch}",
    # simulator.py:167) -- preferred verbatim over any derived
    # composite, per UEF-1's own native-id-preferred convention. No
    # random UUID, no adapter-generated surrogate.
    return build_event_ref(source_namespace=SOURCE_NAMESPACE, native_id=trade.trade_id)


def build_probe_episode(trade: Q11VirtualProbeTrade) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one closed Q11 virtual
    probe trade. Every return/excursion/timestamp figure is taken
    verbatim from the real, already-resolved trade row -- see module
    docstring for why `evaluate_forward()` is never called here."""

    checkpoints = tuple(_forward_checkpoint(trade, label) for label in _FORWARD_HORIZON_LABELS) + (
        _eod_checkpoint(trade), _exit_checkpoint(trade),
    )
    event_ref = _build_probe_event_ref(trade)
    return build_episode_record(
        source_namespace=SOURCE_NAMESPACE, hypothesis_id=HYPOTHESIS_ID, observation_type=ObservationType.SHADOW_ENTRY,
        execution_mode=ExecutionMode.OBSERVATION_ONLY, trading_date=trade.day, symbol=trade.symbol, event_ref=event_ref,
        checkpoints=checkpoints,
        provenance=Provenance(
            legacy_program=HYPOTHESIS_ID, legacy_schema=TRADES_SCHEMA,
            source_artifact=f"{_OPPORTUNITY_ENGINE_SHADOW_DIR}/{trade.day}/{_TRADES_ARTIFACT_FILENAME}",
            source_function="simulate_probe_v0",
        ),
        metadata={
            "trade_id": trade.trade_id, "entry_epoch": trade.entry_epoch, "entry_price": trade.entry_price,
            "exit_reason": trade.exit_reason, "strategy_id": "probe_v0",
        },
    )


def checkpoint_to_net_or_cost_included_member(
    checkpoint: Checkpoint | None,
    *,
    evaluation_record_id: str,
) -> CanonicalAggregationMember:
    """Q11's own copy of the same `NET_OR_COST_INCLUDED` translation
    Q12/Opening Shadow 1B-1C/Q10 Index Calc H each declare independently
    -- every adapter family owns its own translation; the shape is
    identical only because these families happen to share the same cost
    semantics, never because one imports/reuses another's
    implementation."""

    if checkpoint is None or checkpoint.completeness is not CheckpointCompleteness.OBSERVED:
        return CanonicalAggregationMember(state=SampleMemberState.MISSING)
    if checkpoint.net_return is None or checkpoint.observed_timestamp is None:
        raise VirtualProbeAdapterError(
            f"checkpoint_to_net_or_cost_included_member: checkpoint {checkpoint.horizon_label!r} is OBSERVED but "
            "missing net_return/observed_timestamp -- canonical-record consistency defect, never silently treated as MISSING"
        )
    return CanonicalAggregationMember(
        state=SampleMemberState.EVALUATED,
        evaluation_record_id=evaluation_record_id,
        gross_return=None,
        return_unit=checkpoint.return_unit,
        source_cost_semantics=SourceResultCostSemantics.NET_OR_COST_INCLUDED,
        cost_policy=None,
        source_net_return=checkpoint.net_return,
        observed_timestamp=checkpoint.observed_timestamp,
        target_timestamp=checkpoint.target_timestamp,
    )


@dataclass(frozen=True)
class Q11VirtualProbeCanonicalResult:
    """Adapter-local (NOT canonical) per-trade result of the approved Q11
    ingestion path."""

    trade: Q11VirtualProbeTrade
    episode: EpisodeRecord


def canonicalize_q11_opportunity_engine_artifact(path: str | Path) -> list[Q11VirtualProbeCanonicalResult]:
    """The ONE approved, public Q11 ingestion entrypoint.

    1. reads the artifact through its own real, verified origin (family
       path layout + BOTH persisted discriminators,
       `_verify_trades_artifact_origin`) -- never a caller-supplied,
       already-parsed dict;
    2. parses every row into a verified DTO (`Q11VirtualProbeTrade`),
       fail-fast rejecting any row missing/violating
       `order_execution_allowed: False` -- never trusting artifact
       origin alone to guarantee this is virtual, never real execution
       evidence;
    3. canonicalizes: every trade in the real `trades[]` list is, by
       construction, already fully closed (see module docstring) -- one
       trade always becomes exactly one EVALUATED EpisodeRecord, never
       EXCLUDED/MISSING at the trade level. Per-horizon MISSING/PENDING
       semantics are still preserved distinctly within each episode's own
       checkpoints (see `_forward_checkpoint`/`_eod_checkpoint`).
    """

    payload = _verify_trades_artifact_origin(Path(path))
    day = str(payload.get("day") or "")
    trades = payload.get("trades")
    if not isinstance(trades, list):
        raise VirtualProbeAdapterError("canonicalize_q11_opportunity_engine_artifact: artifact.trades must be a list")

    results: list[Q11VirtualProbeCanonicalResult] = []
    for row in trades:
        if not isinstance(row, Mapping):
            continue
        trade = _parse_trade(day, row)
        episode = build_probe_episode(trade)
        results.append(Q11VirtualProbeCanonicalResult(trade=trade, episode=episode))
    return results


__all__ = [
    "VirtualProbeAdapterError",
    "SOURCE_NAMESPACE",
    "HYPOTHESIS_ID",
    "Q11VirtualProbeTrade",
    "Q11VirtualProbeCanonicalResult",
    "checkpoint_to_net_or_cost_included_member",
    "canonicalize_q11_opportunity_engine_artifact",
]
