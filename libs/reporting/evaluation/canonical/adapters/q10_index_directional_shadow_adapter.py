"""UEF-4B-4 -- Q10 Index Calc H canonical adapter: `q10_index_directional_shadow_adapter`.

Source authority (verified directly against real source):
`libs/reporting/baseline_samsung_hynix/forward_validation/shadow_comparison.py`
(`build_shadow_comparison`/`_direction`/`_first_pullback_entry`),
`.../forward_validation/expected_actual.py` (`build_expected_actual` --
the ONLY artifact that always has one row per (day, target), direction
or not), and `.../forward_validation/pipeline.py` (`build_q10_forward_
validation` -- the real writer of every trusted artifact this module
ingests).

H RELATIONSHIP RESOLUTION (this task's Section 7): H is a DIRECTIONAL
HYPOTHESIS over the SAME (day, target) physical observation Calc F/G
already canonicalize (`q10_index_reaction_adapter.py`) -- verified
directly against source: `build_shadow_comparison` reads
`reactions.get("targets")` (the EXACT SAME dict Calc F/G's own
`build_actual_reactions()` produces), reusing its OWN
`points[ENTRY_LABEL]` for 4 of its 5 entry references, its OWN
`points["CLOSE"]` as the exit price, and its OWN candle `path` for
MFE/MAE excursion scanning. H introduces NO new physical instrument, NO
new candle source, NO new symbol. Per this task's Section 16: SAME
physical event identity as the Calc F/G episode for the identical
(day, symbol) pair (this module reuses the exact same `SOURCE_NAMESPACE`
+ `(trading_date, symbol)` derivation as `q10_index_reaction_adapter.py`
so `canonical_event_id` is byte-identical), DIFFERENT evaluation/
hypothesis identity (`HYPOTHESIS_ID_H`, distinct from `HYPOTHESIS_ID_F`/
`HYPOTHESIS_ID_G`).

H's own SAMPLE UNIT is ONE (target, entry policy) pair: `SHADOW_ENTRY_
POLICIES` declares 5 entry policies (ENTRY_0900/0903/0905/0910/FIRST_
PULLBACK_ENTRY), each evaluated for a (day, target) whose expected_state
is non-NEUTRAL -- a Q10-Semiconductor-style multi-VIEW pattern (5
evaluation policies over the SAME physical event + hypothesis), never
5 duplicated physical events. This module's `horizon_label` values are
therefore the 5 policy names, not calendar horizons.

DIRECTION: `_direction(expected_state)` (`shadow_comparison.py:17-22`,
imported and called directly, never reimplemented) maps
POSITIVE/STRONG_POSITIVE/RISK_ON/STRONG_RISK_ON -> +1,
NEGATIVE/STRONG_NEGATIVE/RISK_OFF/STRONG_RISK_OFF -> -1, everything else
(including NEUTRAL) -> 0. A `direction==0` (NEUTRAL) target/day is the
source's OWN population-exclusion rule (`if direction == 0: continue`,
`shadow_comparison.py:80-81`) -- the real `q10_shadow_entry_comparison
.json` artifact NEVER persists an outcome row for it at all (genuinely
absent, not merely unobserved). This module detects this from the
COMPLETE per-target `q10_expected_vs_actual.json` artifact (which always
carries exactly one row per target/day, direction or not) and maps it to
canonical `SampleMemberState.EXCLUDED` -- mirroring Opening Shadow
FIX1/FIX2's exact 1A EXCLUDED-population pattern -- never MISSING, never
a 0-return, never silently dropped merely because the source itself
never persisted a row for it.

RETURN VALUES: `gross_eod_return_pct`/`net_eod_return_pct`/`mfe_pct`/
`mae_pct` (`shadow_comparison.py:98-116`) are ALREADY direction-adjusted,
ALREADY cost-adjusted (net) real legacy values -- taken verbatim into
`Checkpoint.gross_return`/`net_return`/`mfe`/`mae`, never recomputed by
this adapter (irreducibly SOURCE_PROVIDED, matching the frozen
`build_q10_index_calc_h_profile()`'s own
`SourceResultCostSemantics.NET_OR_COST_INCLUDED` classification --
`CostPolicy` must never be reapplied here). That frozen profile's own
fixed `GrossReturnPolicy(direction=TradeDirection.SHORT)` describes ONLY
its own (unused, informational) engine-side gross-return computation --
irrelevant to the verbatim values this module actually stores, since
`evaluate_forward()` is never called for H at all (see next paragraph).

WHY `evaluate_forward()` IS NOT CALLED FOR H: exactly like Calc G (see
`q10_index_reaction_adapter.py`'s own module docstring), H's own entry/
exit references and return/excursion figures are ALL already fully
resolved in the real, persisted `q10_shadow_entry_comparison.json`
artifact (`entry_ts`, `entry_price`, `exit_price`=CLOSE, gross/net/mfe/
mae) -- the SAME "some legacy-verified protocol stays outside the
frozen engine's own observation-matching machinery, the engine only
consumes an already-resolved value" precedent UEF-2A itself already
established for H's `PRE_RESOLVED_REFERENCE` (the 0.5%/60-min
retracement-scan ALGORITHM is explicitly out of UEF-2B's scope) --
extended one step further here to cover ALL of H's outcome fields, not
only its entry reference, because the real legacy `build_shadow_
comparison` already resolves every one of them itself.

EXECUTION BOUNDARY: this module imports nothing from
`opening_rank1_controlled_probe.py`, `controlled_mock_lanes/`, or any
broker/executor/order module -- see `q10_index_reaction_adapter.py`'s
own module docstring for the real, disjoint evaluation-vs-execution
symbol universes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from libs.reporting.baseline_samsung_hynix.forward_validation.contracts import PROGRAM_ID, SCHEMA_VERSION, SHADOW_ENTRY_POLICIES
from libs.reporting.baseline_samsung_hynix.forward_validation.reaction_reader import _checkpoint_epoch
from libs.reporting.baseline_samsung_hynix.forward_validation.shadow_comparison import _direction

from libs.reporting.evaluation.canonical.contracts import CheckpointCompleteness, EventOrigin, ExecutionMode, ObservationType, ReturnUnit
from libs.reporting.evaluation.canonical.forward import SourceResultCostSemantics
from libs.reporting.evaluation.canonical.metrics.aggregation import CanonicalAggregationMember, SampleMemberState
from libs.reporting.evaluation.canonical.record import Checkpoint, EpisodeRecord, Provenance, build_episode_record

from .forward_measurement_adapter import build_forward_measurement_event_ref
from .q10_index_reaction_adapter import (
    Q10IndexAdapterError,
    SOURCE_NAMESPACE,
    _BASELINE_SAMSUNG_HYNIX_DIR,
    _Q10_FORWARD_VALIDATION_DIR,
    _REACTIONS_ARTIFACT_FILENAME,
    _number,
    _parse_reaction_target,
    _read_verified_json,
)


HYPOTHESIS_ID_H = "baseline_samsung_hynix_forward_validation_shadow_comparison"
_EXPECTED_VS_ACTUAL_FILENAME = "q10_expected_vs_actual.json"
_SHADOW_COMPARISON_FILENAME = "q10_shadow_entry_comparison.json"


def policy_hypothesis_id(policy: str) -> str:
    """FIX1 -- bind Calc H's entry-policy dimension into the frozen
    `hypothesis_id` EVALUATION-identity field, never into physical
    identity. Codex's audit: the 5 `SHADOW_ENTRY_POLICIES` are 5
    genuinely different evaluation questions ("what if entry occurred at
    09:00 / 09:03 / 09:05 / 09:10 / at the retracement-scan's own
    FIRST_PULLBACK_ENTRY") over the SAME physical (day, symbol) market
    event that `q10_index_reaction_adapter.py`'s own Calc F/G episode
    already canonicalizes -- `canonical_event_id` stays byte-identical
    across all 5 (derived purely from `source_namespace`+`trading_date`+
    `symbol`, per UEF-1's own `build_derived_event_ref`, never touched
    here), while `evaluation_subject_id`/`evaluation_record_id` (both
    derived, among other shared fields, from `hypothesis_id` -- see
    `identity.py::evaluation_subject_id`/`evaluation_record_id`, frozen,
    unmodified) become policy-distinct through THIS existing dimension.
    No new canonical field, no new canonical id system -- policy is
    additionally preserved verbatim in `Checkpoint.horizon_label` and
    `EpisodeRecord.metadata["policy"]` so it stays independently
    reconstructable from provenance even though it is now also folded
    into the evaluation identity."""

    if policy not in SHADOW_ENTRY_POLICIES:
        raise Q10IndexAdapterError(f"policy_hypothesis_id: unknown policy={policy!r}")
    return f"{HYPOTHESIS_ID_H}_{policy.lower()}"


def checkpoint_to_net_or_cost_included_member(
    checkpoint: Checkpoint | None,
    *,
    evaluation_record_id: str,
    state_override: SampleMemberState | None = None,
) -> CanonicalAggregationMember:
    """Q10 Index Calc H's own copy of the same `NET_OR_COST_INCLUDED`
    translation Q12/Opening Shadow 1B/1C each declare independently --
    every adapter family owns its own translation; the shape is
    identical only because these families happen to share the same cost
    semantics, never because one imports/reuses another's
    implementation."""

    if state_override is SampleMemberState.EXCLUDED:
        return CanonicalAggregationMember(state=SampleMemberState.EXCLUDED)
    if checkpoint is None or checkpoint.completeness is not CheckpointCompleteness.OBSERVED:
        return CanonicalAggregationMember(state=SampleMemberState.MISSING)
    if checkpoint.net_return is None or checkpoint.observed_timestamp is None:
        raise Q10IndexAdapterError(
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
class Q10IndexShadowExclusion:
    """Lineage-preserving record for a Calc H (day, target) whose real
    `expected_state` is NEUTRAL (`_direction()==0`) -- the real
    `build_shadow_comparison` never emits an outcome row for it at all.
    Deliberately NOT a new canonical type -- mirrors Opening Shadow
    FIX1/FIX2's `OpeningShadow1AExclusion` exactly: the canonical
    population state is `SampleMemberState.EXCLUDED` alone, already
    representable without an EpisodeRecord; this dataclass exists purely
    so the exclusion stays traceable (day, symbol, key, expected_state,
    exclusion reason, source provenance), never silently dropped."""

    day: str
    key: str
    symbol: str
    expected_state: str
    exclusion_reason: str
    legacy_program: str
    legacy_schema: str
    source_artifact: str


def _verify_h_artifact_origin(day_dir: Path) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    """Read and verify ALL real trusted artifacts H needs:

    - `q10_expected_vs_actual.json`: complete direction source, one row
      per target/day;
    - `q10_shadow_entry_comparison.json`: H's own outcome rows, with
      direction==0 rows genuinely absent;
    - `q10_actual_market_reactions.json`: the authoritative key->symbol
      mapping, identical to Calc F/G's physical-event source.

    All three pass through the SAME real family-path +
    dual-discriminator verification as Calc F/G's own artifact
    (`_read_verified_json`, shared, never duplicated)."""

    expected = _read_verified_json(day_dir, _EXPECTED_VS_ACTUAL_FILENAME)
    shadow = _read_verified_json(day_dir, _SHADOW_COMPARISON_FILENAME)
    reactions = _read_verified_json(day_dir, _REACTIONS_ARTIFACT_FILENAME)
    return expected, shadow, reactions


def _trusted_symbol_map_from_reactions(day: str, reactions_payload: Mapping[str, Any]) -> dict[str, str]:
    """Derive H's physical symbol authority from the SAME trusted
    `q10_actual_market_reactions.json` artifact Calc F/G canonicalize.
    This deliberately removes caller-supplied `target_symbols` as a
    public authority: H may receive only `day_dir`; every symbol used in
    a canonical event id must come from a verified source artifact."""

    reactions_day = str(reactions_payload.get("day") or "")
    if reactions_day != day:
        raise Q10IndexAdapterError(
            f"_trusted_symbol_map_from_reactions: expected day={day!r} but reactions artifact day={reactions_day!r}"
        )
    targets = reactions_payload.get("targets")
    if not isinstance(targets, Mapping):
        raise Q10IndexAdapterError("_trusted_symbol_map_from_reactions: q10_actual_market_reactions.json.targets must be an object")
    symbol_by_key: dict[str, str] = {}
    for key, row in targets.items():
        if not isinstance(row, Mapping):
            raise Q10IndexAdapterError(f"_trusted_symbol_map_from_reactions: target={key!r} is not an object")
        target = _parse_reaction_target(day=day, key=str(key), row=row)
        symbol_by_key[target.key] = target.symbol
    return symbol_by_key


@dataclass(frozen=True)
class Q10IndexShadowCandidate:
    day: str
    key: str
    symbol: str
    expected_state: str
    direction: int


def _parse_expected_rows(day: str, expected_payload: Mapping[str, Any], *, symbol_by_key: Mapping[str, str]) -> list[Q10IndexShadowCandidate]:
    rows = expected_payload.get("rows")
    if not isinstance(rows, list):
        raise Q10IndexAdapterError("_parse_expected_rows: q10_expected_vs_actual.json.rows must be a list")
    candidates: list[Q10IndexShadowCandidate] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key = str(row.get("target") or "").strip()
        if not key:
            raise Q10IndexAdapterError("_parse_expected_rows: row has no target")
        symbol = symbol_by_key.get(key)
        if not symbol:
            raise Q10IndexAdapterError(f"_parse_expected_rows: target={key!r} has no known symbol -- unknown Q10 Index target key")
        expected_state = str(row.get("expected_state") or "NEUTRAL")
        candidates.append(Q10IndexShadowCandidate(day=day, key=key, symbol=symbol, expected_state=expected_state, direction=_direction(expected_state)))
    return candidates


def _outcome_rows_for_key(shadow_payload: Mapping[str, Any], key: str, policy: str) -> Mapping[str, Any] | None:
    outcomes = shadow_payload.get("outcomes")
    if not isinstance(outcomes, list):
        raise Q10IndexAdapterError("_outcome_rows_for_key: q10_shadow_entry_comparison.json.outcomes must be a list")
    for row in outcomes:
        if isinstance(row, Mapping) and str(row.get("target") or "") == key and str(row.get("policy") or "") == policy:
            return row
    return None


def _build_h_exclusion_record(candidate: Q10IndexShadowCandidate, *, source_artifact: str) -> Q10IndexShadowExclusion:
    if candidate.direction != 0:
        raise Q10IndexAdapterError(f"_build_h_exclusion_record: key={candidate.key!r} has non-NEUTRAL expected_state={candidate.expected_state!r} -- not an exclusion candidate")
    return Q10IndexShadowExclusion(
        day=candidate.day, key=candidate.key, symbol=candidate.symbol, expected_state=candidate.expected_state,
        exclusion_reason=f"neutral_expected_state:{candidate.expected_state}",
        legacy_program=HYPOTHESIS_ID_H, legacy_schema=SCHEMA_VERSION, source_artifact=source_artifact,
    )


def _build_h_episode(candidate: Q10IndexShadowCandidate, outcome: Mapping[str, Any], *, source_artifact: str) -> EpisodeRecord:
    """Build ONE canonical `EpisodeRecord` for one Calc H (target,
    policy) shadow outcome. Every return/excursion figure is taken
    verbatim from the real, already-resolved outcome row -- see module
    docstring for why `evaluate_forward()` is never called here."""

    if candidate.direction == 0:
        raise Q10IndexAdapterError(f"_build_h_episode: key={candidate.key!r} has NEUTRAL expected_state -- use _build_h_exclusion_record instead")
    policy = str(outcome.get("policy") or "")
    status = str(outcome.get("status") or "")
    if status != "OBSERVED":
        raise Q10IndexAdapterError(
            f"_build_h_episode: key={candidate.key!r} policy={policy!r} outcome.status={status!r} is not OBSERVED -- "
            "caller must treat this as a MISSING population member instead of building an episode for it"
        )
    entry_price = _number(outcome.get("entry_price"))
    exit_price = _number(outcome.get("exit_price"))
    entry_ts = int(outcome.get("entry_ts") or 0)
    gross = _number(outcome.get("gross_eod_return_pct"))
    net = _number(outcome.get("net_eod_return_pct"))
    if entry_price is None or entry_price <= 0 or exit_price is None or exit_price <= 0 or entry_ts <= 0:
        raise Q10IndexAdapterError(f"_build_h_episode: key={candidate.key!r} policy={policy!r} OBSERVED outcome has invalid entry/exit price or timestamp")
    if gross is None or net is None:
        raise Q10IndexAdapterError(
            f"_build_h_episode: key={candidate.key!r} policy={policy!r} is OBSERVED but missing gross_eod_return_pct/"
            "net_eod_return_pct -- canonical-record consistency defect, never silently reconciled"
        )
    mfe = _number(outcome.get("mfe_pct"))
    mae = _number(outcome.get("mae_pct"))
    close_ts = _checkpoint_epoch(candidate.day, "CLOSE")
    checkpoint = Checkpoint(
        horizon_label=policy, horizon_origin=EventOrigin.FIXED_CLOCK, target_timestamp=close_ts,
        observed_timestamp=close_ts, observed_price=exit_price, gross_return=gross, net_return=net,
        mfe=mfe, mae=mae, completeness=CheckpointCompleteness.OBSERVED, source=HYPOTHESIS_ID_H,
        horizon_set_id=HYPOTHESIS_ID_H, return_unit=ReturnUnit.PERCENTAGE_POINTS,
    )
    # FIX1: canonical_event_id is derived purely from (source_namespace,
    # trading_date, symbol) -- unaffected by policy, so all 5 policies
    # for the same (day,symbol) share it (physical identity unchanged).
    event_ref = build_forward_measurement_event_ref(source_namespace=SOURCE_NAMESPACE, trading_date=candidate.day, symbol=candidate.symbol)
    hypothesis_id = policy_hypothesis_id(policy)
    return build_episode_record(
        source_namespace=SOURCE_NAMESPACE, hypothesis_id=hypothesis_id, observation_type=ObservationType.SHADOW_ENTRY,
        execution_mode=ExecutionMode.OBSERVATION_ONLY, trading_date=candidate.day, symbol=candidate.symbol, event_ref=event_ref,
        checkpoints=(checkpoint,),
        provenance=Provenance(legacy_program=HYPOTHESIS_ID_H, legacy_schema=SCHEMA_VERSION, source_artifact=source_artifact, source_function="build_shadow_comparison"),
        metadata={"key": candidate.key, "policy": policy, "expected_state": candidate.expected_state, "direction": candidate.direction, "entry_ts": entry_ts},
    )


@dataclass(frozen=True)
class Q10IndexShadowCanonicalResult:
    """Adapter-local (NOT canonical) per-(target,policy) result of the
    approved Calc H ingestion path. Exactly one of `episode`/`exclusion`
    is ever populated; both are `None` only for a non-NEUTRAL candidate
    whose entry never resolved (a MISSING population member -- `member.
    state` reflects this)."""

    key: str
    policy: str
    member: CanonicalAggregationMember
    episode: EpisodeRecord | None
    exclusion: Q10IndexShadowExclusion | None


def canonicalize_q10_index_calc_h_artifact(day_dir: str | Path) -> list[Q10IndexShadowCanonicalResult]:
    """The ONE approved, public Calc H ingestion entrypoint.

    1. reads all trusted artifacts through their own real, verified
       origin (`_verify_h_artifact_origin`) -- never a caller-supplied,
       already-parsed dict;
    2. determines direction from the COMPLETE `q10_expected_vs_actual
       .json` (never the possibly-incomplete `outcomes` list alone);
    3. derives `(target key -> symbol)` from the trusted
       `q10_actual_market_reactions.json` artifact, never from a
       caller-supplied mapping;
    4. applies the population gate immediately: a NEUTRAL (direction==0)
       target/day becomes `SampleMemberState.EXCLUDED` with full lineage
       (`Q10IndexShadowExclusion`); a non-NEUTRAL target/day is evaluated
       once per `SHADOW_ENTRY_POLICIES` entry, EVALUATED when the real
       outcome row is OBSERVED, MISSING when it is PENDING (no
       resolvable entry) -- there is no way to reach a normal
       EpisodeRecord for a NEUTRAL target through this function.

    `q10_expected_vs_actual.json` itself only carries the `key`, never
    the symbol (verified against `expected_actual.py::build_expected_
    actual`). That is why this function reads the trusted reactions
    artifact as part of its own public ingestion boundary rather than
    accepting a symbol map from the caller.
    """

    day_dir = Path(day_dir)
    expected_payload, shadow_payload, reactions_payload = _verify_h_artifact_origin(day_dir)
    day = str(expected_payload.get("day") or "")
    candidates = _parse_expected_rows(day, expected_payload, symbol_by_key=_trusted_symbol_map_from_reactions(day, reactions_payload))
    source_artifact = f"{_BASELINE_SAMSUNG_HYNIX_DIR}/{day}/{_Q10_FORWARD_VALIDATION_DIR}/{_SHADOW_COMPARISON_FILENAME}"

    results: list[Q10IndexShadowCanonicalResult] = []
    for candidate in candidates:
        if candidate.direction == 0:
            exclusion = _build_h_exclusion_record(candidate, source_artifact=source_artifact)
            for policy in SHADOW_ENTRY_POLICIES:
                member = checkpoint_to_net_or_cost_included_member(None, evaluation_record_id="", state_override=SampleMemberState.EXCLUDED)
                results.append(Q10IndexShadowCanonicalResult(key=candidate.key, policy=policy, member=member, episode=None, exclusion=exclusion))
            continue
        for policy in SHADOW_ENTRY_POLICIES:
            outcome = _outcome_rows_for_key(shadow_payload, candidate.key, policy)
            if outcome is None or str(outcome.get("status") or "") != "OBSERVED":
                member = CanonicalAggregationMember(state=SampleMemberState.MISSING)
                results.append(Q10IndexShadowCanonicalResult(key=candidate.key, policy=policy, member=member, episode=None, exclusion=None))
                continue
            episode = _build_h_episode(candidate, outcome, source_artifact=source_artifact)
            member = checkpoint_to_net_or_cost_included_member(episode.checkpoints[0], evaluation_record_id=episode.identity.evaluation_record_id)
            results.append(Q10IndexShadowCanonicalResult(key=candidate.key, policy=policy, member=member, episode=episode, exclusion=None))
    return results


__all__ = [
    "HYPOTHESIS_ID_H",
    "policy_hypothesis_id",
    "Q10IndexShadowExclusion",
    "Q10IndexShadowCanonicalResult",
    "checkpoint_to_net_or_cost_included_member",
    "canonicalize_q10_index_calc_h_artifact",
]
