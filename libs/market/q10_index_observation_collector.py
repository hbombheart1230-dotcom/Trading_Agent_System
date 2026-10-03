from __future__ import annotations

import json
import os
import time
from datetime import date, datetime, time as clock_time
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from zoneinfo import ZoneInfo
from libs.market.q10_observation_integrity import atomic_write, manifest_lock, valid_price, verified_components

# 2026-09-05 PRE-STEP5C cleanup (Codex independent audit, item 3): Q10 Index
# EOD close had no dedicated observation-acquisition path.
#
# 2026-09-05 PRE-STEP5C CLEANUP FIX 3 (second independent Codex re-audit,
# REJECTed FIX 2): a deeper architectural problem, not just a window-size
# bug. FIX 2's "capture window" approach only ever proved that a fetch
# happened at roughly the right LOCAL wall-clock time -- it never proved
# the returned price actually BELONGS to the requested slot, or that a
# CLOSE-slot fetch reflects the true, SETTLED final close (a live 15:30:xx
# quote can be mid-auction, not yet finalized). Direct inspection of
# KiwoomMarketIndexReader.get_index_snapshot / MarketIndexSnapshot
# confirms: the kiwoom.ka20009 response exposes no intraday market-side
# timestamp at all, and no close-finalized/session-status field -- only a
# DATE-granularity `current_date` (from the response's own `dt_n`). There
# is therefore NO evidence-based way to VERIFY, from this API alone, that
# a captured price is the requested slot's price or a true final close.
#
# Fix: local request-time proximity is no longer treated as verification.
# A successful capture within the local capture window is recorded as
# OBSERVED_UNVERIFIED_TIME (09:30/10:00) or CLOSE_UNVERIFIED (CLOSE) --
# informational, persisted, but NEVER fed into Q10 return/scoring/reaction
# calculations (see reaction_reader.py's collector_override, which only
# treats AVAILABLE/PARTIAL -- the genuinely evidence-verified states -- as
# calculation-usable). `_has_verification_evidence()` is evidence-driven:
# it inspects each component for real market-side timestamp/close-
# finalized fields and only returns True if such evidence is present and
# consistent -- with the current reader contract this is always False for
# real data, so AVAILABLE/PARTIAL are correctly unreachable today, but the
# mechanism activates automatically the moment genuine evidence becomes
# available (a reader enhancement, or a test fixture), with no further
# changes needed here.
#
# item 3 (persistent claim): rebuilt as "Option A -- strict at-most-once
# measurement" per Codex's own explicit menu. A claim is a single atomic
# exclusive-create (same primitive as libs/runtime/live_loop_lock.py::
# acquire_live_loop_lock), and the instant it is won, a durable
# ATTEMPT_INCOMPLETE marker is persisted to the MANIFEST itself (not just
# the claim file) BEFORE the live API is ever called. From that point on,
# NOTHING may automatically retry that slot again -- not a dead claim-
# owner pid, not staleness, nothing. A crash between the claim and the
# final result is accepted, permanent data loss for that one slot that
# day, in exchange for a hard guarantee against ever duplicating a live
# measurement. This is deliberately much stricter than FIX 2's claim
# (which allowed dead-pid/stale-claim reclaim -- exactly what Codex's
# re-audit rejected).
#
# item 4 (manifest structural validation): a manifest file that exists
# but is not a well-formed, day-matching structure (wrong top-level type,
# `[]`, a different day recorded inside it, malformed slot rows) is
# ManifestCorruptError, never silently reset to an empty/fresh state --
# only a genuinely ABSENT file may start fresh.
#
# item 5/6 (component-level validation, invalid-vs-absent): each index
# component (KOSPI/KOSDAQ) is validated independently -- a component
# whose own `current_date` disagrees with the requested day is excluded
# from `indices` (tracked separately in `rejected_components`), never
# silently counted toward completeness. AVAILABLE/OBSERVED_UNVERIFIED_TIME
# require ALL required components to individually pass validation, never
# merely `len(indices) == 2`. A closeout recovery merge never overwrites
# an already-confirmed component, and never merges in a component from a
# recovery fetch that was itself LATE_MISSED/MISSING.

KST = ZoneInfo("Asia/Seoul")
SCHEMA_VERSION = "q10_index_observation.v3"
DEFAULT_SLOTS = ("09:30", "10:00", "15:30")
DEFAULT_OBSERVATION_ROOT = Path("data/logs/q10_index_observations")
_REQUIRED_INDEX_NAMES = frozenset({"KOSPI", "KOSDAQ"})

# Evidence-verified, calculation-usable states (currently unreachable given
# the reader's actual contract -- see _has_verification_evidence).
_VERIFIED_COMPLETE_STATES = frozenset({"AVAILABLE"})
_VERIFIED_PARTIAL_STATES = frozenset({"PARTIAL"})
# Captured-but-unverified states -- informational only, never usable for
# Q10 return/scoring/reaction calculations.
_UNVERIFIED_COMPLETE_STATES = frozenset({"OBSERVED_UNVERIFIED_TIME", "CLOSE_UNVERIFIED"})
_UNVERIFIED_PARTIAL_STATES = frozenset({"PARTIAL_UNVERIFIED"})
_COMPLETE_STATES = _VERIFIED_COMPLETE_STATES | _UNVERIFIED_COMPLETE_STATES
_PARTIAL_STATES = _VERIFIED_PARTIAL_STATES | _UNVERIFIED_PARTIAL_STATES
# Every state a captured (non-never-attempted) row can be in -- used by
# reaction_reader.py to distinguish ABSENT (no row at all -> legacy
# fallback allowed) from INVALID/UNVERIFIED (a row exists but is not
# calculation-usable -> fallback forbidden, integrity failure surfaced).
_ALL_ATTEMPTED_STATES = _COMPLETE_STATES | _PARTIAL_STATES | frozenset(
    {"MISSING", "LATE_MISSED", "CORRUPT_STATE", "ATTEMPT_INCOMPLETE"}
)

DEFAULT_PRIMARY_WINDOW_SEC = 5 * 60
DEFAULT_CLOSEOUT_WINDOW_SEC = 15 * 60


class ManifestCorruptError(RuntimeError):
    """Raised when the persistent slot-observation manifest file exists
    but is not a well-formed, day-matching structure. MUST NOT be caught
    and silently treated as an empty/fresh manifest."""


def default_indices() -> tuple[str, ...]:
    return ("KOSPI", "KOSDAQ")


def _slot_epoch(day: str, slot: str) -> int:
    hour_str, minute_str = str(slot).split(":", 1)
    parsed_day = date.fromisoformat(str(day)[:10])
    return int(
        datetime.combine(parsed_day, clock_time(int(hour_str), int(minute_str)), tzinfo=KST).timestamp()
    )


def capture_q10_index_snapshot(
    *,
    indices: Iterable[str] = ("KOSPI", "KOSDAQ"),
    reader_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """One live fetch via KiwoomMarketIndexReader (kiwoom.ka20009). Never
    raises: a failure comes back as an 'unavailable' status payload."""
    try:
        if reader_factory is None:
            from libs.read.kiwoom_market_index_reader import KiwoomMarketIndexReader

            reader_factory = KiwoomMarketIndexReader.from_env
        reader = reader_factory()
        return dict(reader.get_index_packet(tuple(indices)))
    except Exception as exc:
        return {
            "status": "unavailable",
            "source": "kiwoom.ka20009",
            "indices": {},
            "error": f"{type(exc).__name__}: {exc}",
        }


def _manifest_path(day: str, *, root: Path | str | None = None) -> Path:
    base = Path(root or DEFAULT_OBSERVATION_ROOT)
    return base / str(day)[:10] / "capture_manifest.json"


def _empty_manifest(day: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": "observation_only",
        "day": str(day)[:10],
        "slots": [],
    }


def _validate_manifest_structure(value: Any, day: str) -> dict[str, Any]:
    """2026-09-05 FIX 3 (item 4): a manifest that parses as JSON but has
    the wrong shape must never be silently treated as empty/fresh."""
    if not isinstance(value, Mapping):
        raise ManifestCorruptError(f"top_level_not_dict:{type(value).__name__}")
    manifest_day = value.get("day")
    if manifest_day != day:
        raise ManifestCorruptError(f"day_mismatch:{manifest_day!r}!={day!r}")
    slots = value.get("slots")
    if not isinstance(slots, list):
        raise ManifestCorruptError(f"slots_not_list:{type(slots).__name__}")
    validated_slots: list[dict[str, Any]] = []
    seen = set()
    for row in slots:
        if not isinstance(row, Mapping):
            raise ManifestCorruptError(f"slot_row_not_dict:{type(row).__name__}")
        requested_slot = row.get("requested_slot")
        if requested_slot not in DEFAULT_SLOTS or requested_slot in seen:
            raise ManifestCorruptError("slot_row_missing_requested_slot")
        if row.get('availability') not in _ALL_ATTEMPTED_STATES:
            raise ManifestCorruptError('slot_state_invalid')
        if not isinstance(row.get('indices', {}), Mapping):
            raise ManifestCorruptError('slot_indices_invalid')
        seen.add(requested_slot)
        validated_slots.append(dict(row))
    return {
        "schema_version": SCHEMA_VERSION,
        "behavior_effect": "observation_only",
        "day": day,
        "slots": validated_slots,
    }


def _read_manifest(path: Path, day: str) -> dict[str, Any]:
    day = str(day)[:10]
    if not path.exists():
        return _empty_manifest(day)
    try:
        raw = path.read_text(encoding="utf-8")
        value = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManifestCorruptError(f"{path}: {type(exc).__name__}: {exc}") from exc
    return _validate_manifest_structure(value, day)


def _write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n"
    atomic_write(path, content)


def _persist_row(day: str, row: Mapping[str, Any], *, root: Path | str | None = None) -> None:
    day = str(day)[:10]
    manifest_path = _manifest_path(day, root=root)
    manifest = _read_manifest(manifest_path, day)
    slot = row.get("requested_slot")
    manifest["slots"] = [item for item in manifest["slots"] if item.get("requested_slot") != slot]
    manifest["slots"].append(dict(row))
    manifest["slots"].sort(key=lambda item: str(item.get("requested_slot") or ""))
    _write_manifest(manifest_path, manifest)


def _corrupt_state_row(slot: str, *, reason: str) -> dict[str, Any]:
    return {
        "requested_slot": str(slot),
        "requested_at_kst": None,
        "actual_observed_at_kst": None,
        "actual_lag_sec": None,
        "availability": "CORRUPT_STATE",
        "capture_status": "CORRUPT_STATE",
        "source": "",
        "source_market_timestamp": None,
        "source_market_timestamp_available": False,
        "indices": {},
        "rejected_components": {},
        "error": reason,
        "closeout_requeried": False,
        "logical_capture_attempt_count": 0,
        "logical_closeout_requery_count": 0,
        "physical_request_attempt_count": None,
        "physical_request_attempt_count_available": False,
    }


def _missing_placeholder(slot: str) -> dict[str, Any]:
    return {
        "requested_slot": str(slot),
        "requested_at_kst": None,
        "actual_observed_at_kst": None,
        "actual_lag_sec": None,
        "availability": "MISSING",
        "capture_status": "MISSING",
        "source": "",
        "source_market_timestamp": None,
        "source_market_timestamp_available": False,
        "indices": {},
        "rejected_components": {},
        "error": "not_yet_captured",
        "closeout_requeried": False,
        "logical_capture_attempt_count": 0,
        "logical_closeout_requery_count": 0,
        "physical_request_attempt_count": None,
        "physical_request_attempt_count_available": False,
    }


def _attempt_incomplete_row(slot: str, requested_at_epoch: int, observed_epoch: int) -> dict[str, Any]:
    """2026-09-05 FIX 3 (item 3, Option A): the durable "point of no
    return" marker, persisted BEFORE the live API is called. If the
    process crashes after this write, the slot stays ATTEMPT_INCOMPLETE
    forever -- never automatically retried by anything."""
    return {
        "requested_slot": str(slot),
        "requested_at_kst": datetime.fromtimestamp(requested_at_epoch, tz=KST).isoformat(timespec="seconds"),
        "actual_observed_at_kst": datetime.fromtimestamp(observed_epoch, tz=KST).isoformat(timespec="seconds"),
        "actual_lag_sec": max(0, int(observed_epoch - requested_at_epoch)),
        "availability": "ATTEMPT_INCOMPLETE",
        "capture_status": "ATTEMPT_INCOMPLETE",
        "source": "",
        "source_market_timestamp": None,
        "source_market_timestamp_available": False,
        "indices": {},
        "rejected_components": {},
        "error": "attempt_started_result_not_yet_persisted",
        "closeout_requeried": False,
        "logical_capture_attempt_count": 1,
        "logical_closeout_requery_count": 0,
        "physical_request_attempt_count": None,
        "physical_request_attempt_count_available": False,
    }


def load_observations(day: str, *, root: Path | str | None = None) -> list[dict[str, Any]]:
    """Raises ManifestCorruptError if the manifest file exists but is not
    well-formed."""
    return list(_read_manifest(_manifest_path(day, root=root), str(day)[:10])["slots"])


def observation_for_slot(day: str, slot: str, *, root: Path | str | None = None) -> dict[str, Any]:
    try:
        rows = load_observations(day, root=root)
    except ManifestCorruptError as exc:
        return _corrupt_state_row(slot, reason=f"manifest_corrupt:{exc}")
    row = next((item for item in rows if item.get("requested_slot") == slot), None)
    if row is not None:
        return dict(row)
    if _claim_path(day, slot, root=root).exists():
        return _corrupt_state_row(slot, reason='claim_without_persisted_result')
    result = _missing_placeholder(slot)
    result['never_attempted'] = True
    return result


# --- item 3: persistent, cross-process, at-most-once slot claim --------


def _claims_dir(day: str, *, root: Path | str | None = None) -> Path:
    return _manifest_path(day, root=root).parent / "claims"


def _claim_path(day: str, slot: str, *, root: Path | str | None = None) -> Path:
    safe_slot = str(slot).replace(":", "")
    return _claims_dir(day, root=root) / f"{safe_slot}.claim.json"


def _acquire_slot_claim(
    day: str, slot: str, *, root: Path | str | None = None, current_pid: int | None = None,
) -> bool:
    """2026-09-05 FIX 3 (item 3, Option A -- strict at-most-once): a
    single atomic exclusive-create (open(path, "x"), the same primitive
    already proven by libs/runtime/live_loop_lock.py::
    acquire_live_loop_lock -- atomic at the OS filesystem level across
    real, separate OS processes, not just threads). Deliberately NO
    staleness or dead-pid reclaim logic -- once a claim file exists, it
    is never reclaimed by anyone. The claim's only job is to gate the
    brief race of transitioning a slot from never-attempted to durably
    ATTEMPT_INCOMPLETE; once that transition is durably in the manifest,
    the manifest itself (not the claim) is what permanently blocks any
    further attempt."""
    path = _claim_path(day, slot, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": int(current_pid if current_pid is not None else os.getpid()),
        "claimed_at_epoch": int(time.time()),
        "day": str(day)[:10],
        "requested_slot": str(slot),
    }
    try:
        with open(path, "x", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False))
            file.flush()
            os.fsync(file.fileno())
        return True
    except FileExistsError:
        return False
    except Exception:
        return False


def _release_slot_claim(day: str, slot: str, *, root: Path | str | None = None) -> None:
    # Permanent attempt receipt: even a crash before the manifest write
    # must not authorize another measurement.
    return None


# --- item 1/5/6: evidence-driven classification -------------------------


def _has_verification_evidence(indices: Mapping[str, Mapping[str, Any]], *, slot: str, day: str = '', observed_epoch: int = 0) -> bool:
    """2026-09-05 FIX 3 (item 1): see module docstring. Evidence-driven,
    not request-timing-driven -- always False against kiwoom.ka20009's
    actual (timestamp-less, close-status-less) contract."""
    return bool(day) and verified_components(indices, scheduled_epoch=_slot_epoch(day, slot), observed_epoch=observed_epoch, is_close=slot == '15:30')


def _classify_row(
    *, day: str, slot: str, scheduled_at_epoch: int, observed_epoch: int,
    packet: Mapping[str, Any], window_sec: int,
) -> dict[str, Any]:
    indices_raw = packet.get("indices") if isinstance(packet.get("indices"), Mapping) else {}
    expected_date = str(day)[:10].replace("-", "")
    lag = observed_epoch - scheduled_at_epoch
    within_window = 0 <= lag <= int(window_sec)

    # item 5/6: each component validated INDEPENDENTLY -- a component
    # whose own current_date disagrees with the requested day is excluded
    # from `indices`, never silently counted toward completeness.
    valid_indices: dict[str, Any] = {}
    rejected_components: dict[str, Any] = {}
    for name, row in indices_raw.items():
        if not isinstance(row, Mapping):
            continue
        row = dict(row)
        if str(name) not in _REQUIRED_INDEX_NAMES or not valid_price(row):
            rejected_components[str(name)] = {'reason': 'invalid_index_price'}
            continue
        candidate_date = str(row.get("current_date") or "").strip()
        if candidate_date and candidate_date != expected_date:
            rejected_components[str(name)] = {"reason": "component_date_mismatch", "current_date": candidate_date}
            continue
        valid_indices[str(name)] = row

    source_market_timestamp = ""
    for row in valid_indices.values():
        candidate = str(row.get("current_date") or "").strip()
        if candidate:
            source_market_timestamp = candidate
            break
    source_market_timestamp_available = bool(source_market_timestamp)

    is_close = slot == "15:30"
    complete = _REQUIRED_INDEX_NAMES <= set(valid_indices)
    verified = _has_verification_evidence(valid_indices, slot=slot, day=day, observed_epoch=observed_epoch)

    if not within_window:
        availability = "LATE_MISSED"
        error = "outside_capture_window"
    elif not valid_indices:
        availability = "MISSING"
        error = str(packet.get("error") or "") or ("all_components_date_mismatch" if rejected_components else "")
    elif complete:
        if verified:
            availability = "AVAILABLE"
        else:
            availability = "CLOSE_UNVERIFIED" if is_close else "OBSERVED_UNVERIFIED_TIME"
        error = ""
    else:
        availability = "PARTIAL" if verified else "PARTIAL_UNVERIFIED"
        error = ""

    requested_at_text = datetime.fromtimestamp(scheduled_at_epoch, tz=KST).isoformat(timespec="seconds")
    observed_at_text = datetime.fromtimestamp(observed_epoch, tz=KST).isoformat(timespec="seconds")
    return {
        "requested_slot": str(slot),
        "requested_at_kst": requested_at_text,
        "actual_observed_at_kst": observed_at_text,
        "actual_lag_sec": max(0, int(lag)),
        "availability": availability,
        "capture_status": availability,
        "source": str(packet.get("source") or "kiwoom.ka20009"),
        "source_market_timestamp": source_market_timestamp or None,
        "source_market_timestamp_available": source_market_timestamp_available,
        "capture_window_sec": int(window_sec),
        "within_capture_window": within_window,
        "verification_evidence_present": verified,
        "indices": valid_indices,
        "rejected_components": rejected_components,
        "error": error or str(packet.get("error") or ""),
        "closeout_requeried": False,
        "logical_capture_attempt_count": 1,
        "logical_closeout_requery_count": 0,
        "physical_request_attempt_count": None,
        "physical_request_attempt_count_available": False,
    }


def capture_slot(
    *,
    day: str,
    slot: str,
    root: Path | str | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(KST),
    capture: Callable[..., Mapping[str, Any]] = capture_q10_index_snapshot,
    extra_fields: Mapping[str, Any] | None = None,
    window_sec: int | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Strict at-most-once capture (2026-09-05 FIX 3, item 3, Option A).

    - A corrupt manifest blocks any capture attempt entirely -- returns
      CORRUPT_STATE, zero live API calls.
    - If any row already exists for this slot (any terminal state at
      all), this is a no-op UNLESS `force=True` (used only by
      closeout_requery_if_missing's bounded, once-only recovery).
    - Otherwise: acquires the atomic claim (zero API calls if another
      process already holds it or has already recorded any row), then
      IMMEDIATELY persists a durable ATTEMPT_INCOMPLETE marker BEFORE
      calling the live API -- from that point on, this slot is
      permanently claimed even if the process crashes before the real
      result is ever persisted.
    """
    day = str(day)[:10]
    try:
        rows = load_observations(day, root=root)
    except ManifestCorruptError as exc:
        return _corrupt_state_row(slot, reason=f"manifest_corrupt:{exc}")

    existing = next((row for row in rows if row.get("requested_slot") == slot), None)
    if not force and existing is not None:
        return dict(existing)

    with manifest_lock(_manifest_path(day, root=root)):
        current = observation_for_slot(day, slot, root=root)
        if current.get('availability') == 'CORRUPT_STATE':
            return current
        if force:
            if current.get('availability') not in {'MISSING', 'LATE_MISSED', 'PARTIAL', 'PARTIAL_UNVERIFIED'} or current.get('closeout_requeried'):
                return current
        elif not current.get('never_attempted'):
            return current
        claim_slot = slot + '_recovery' if force else slot
        if not _acquire_slot_claim(day, claim_slot, root=root):
            return _corrupt_state_row(slot, reason='attempt_claim_already_exists')
        scheduled_epoch = _slot_epoch(day, slot)
        observed_epoch = int(now_fn().astimezone(KST).timestamp())
        marker = _attempt_incomplete_row(slot, scheduled_epoch, observed_epoch)
        marker['closeout_requeried'] = force
        marker['logical_closeout_requery_count'] = int(force)
        marker['logical_capture_attempt_count'] = int(current.get('logical_capture_attempt_count') or 0) + 1
        _persist_row(day, marker, root=root)
    try:
        packet = dict(capture())
    except Exception as exc:
        packet = {'status': 'unavailable', 'indices': {}, 'error': f'{type(exc).__name__}: {exc}'}
    with manifest_lock(_manifest_path(day, root=root)):
        observed_epoch = int(now_fn().astimezone(KST).timestamp())
        effective_window = int(window_sec) if window_sec is not None else DEFAULT_PRIMARY_WINDOW_SEC
        row = _classify_row(
            day=day, slot=slot, scheduled_at_epoch=scheduled_epoch, observed_epoch=observed_epoch,
            packet=packet, window_sec=effective_window,
        )
        if extra_fields:
            row.update(dict(extra_fields))
        if force and current.get('availability') in _PARTIAL_STATES:
            merged = dict(current.get('indices') or {})
            if row['availability'] in {'LATE_MISSED', 'MISSING'}:
                row = dict(current)
            else:
                for name, component in row['indices'].items():
                    merged.setdefault(name, component)
                row = _classify_row(day=day, slot=slot, scheduled_at_epoch=scheduled_epoch,
                                    observed_epoch=observed_epoch, packet={'indices': merged}, window_sec=effective_window)
        row['closeout_requeried'] = force
        row['logical_closeout_requery_count'] = int(force)
        row['logical_capture_attempt_count'] = marker['logical_capture_attempt_count']
        _persist_row(day, row, root=root)
        return row


def closeout_requery_if_missing(
    *,
    day: str,
    slot: str = "15:30",
    root: Path | str | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(KST),
    capture: Callable[..., Mapping[str, Any]] = capture_q10_index_snapshot,
    window_sec: int = DEFAULT_CLOSEOUT_WINDOW_SEC,
    min_ready_grace_sec: int = DEFAULT_PRIMARY_WINDOW_SEC,
) -> dict[str, Any]:
    """Bounded, one-shot LOGICAL re-query at closeout. Eligible for
    MISSING/LATE_MISSED (no merge needed) and PARTIAL/PARTIAL_UNVERIFIED
    (component-level merge -- item 5/6: an already-confirmed component is
    never overwritten, and a component is only merged in if the recovery
    fetch's OWN classification did not reject it; if the recovery fetch
    itself is LATE_MISSED/MISSING, nothing is merged in, but the bounded
    attempt is still marked consumed). CORRUPT_STATE/ATTEMPT_INCOMPLETE
    are never touched automatically.

    Always safe to call at any time of day: refuses to act before
    `scheduled_epoch + min_ready_grace_sec` has elapsed."""
    day = str(day)[:10]
    scheduled_epoch = _slot_epoch(day, slot)
    now_epoch = int(now_fn().astimezone(KST).timestamp())
    if now_epoch < scheduled_epoch + max(0, int(min_ready_grace_sec)):
        return observation_for_slot(day, slot, root=root)

    current = observation_for_slot(day, slot, root=root)
    availability = str(current.get("availability") or "")
    if availability in _COMPLETE_STATES or availability in ("CORRUPT_STATE", "ATTEMPT_INCOMPLETE"):
        return current
    if bool(current.get("closeout_requeried")):
        return current

    return capture_slot(
        day=day, slot=slot, root=root, now_fn=now_fn, capture=capture,
        extra_fields={"closeout_requeried": True, "logical_closeout_requery_count": 1},
        window_sec=window_sec, force=True,
    )


def run_due_slots(
    *,
    day: str,
    root: Path | str | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(KST),
    capture: Callable[..., Mapping[str, Any]] = capture_q10_index_snapshot,
    slots: Iterable[str] = DEFAULT_SLOTS,
    closeout_grace_sec: int = DEFAULT_PRIMARY_WINDOW_SEC,
    window_sec: int = DEFAULT_PRIMARY_WINDOW_SEC,
    closeout_window_sec: int = DEFAULT_CLOSEOUT_WINDOW_SEC,
) -> list[dict[str, Any]]:
    """Called once per poll cycle by scripts/run_q10_index_observation_
    collector.py. A corrupt persistent manifest blocks ALL captures for
    the day (fail-honest)."""
    day = str(day)[:10]
    slots = list(slots) or list(DEFAULT_SLOTS)
    now_epoch = int(now_fn().astimezone(KST).timestamp())

    try:
        load_observations(day, root=root)
    except ManifestCorruptError as exc:
        return [_corrupt_state_row("*", reason=f"manifest_corrupt:{exc}")]

    captured: list[dict[str, Any]] = []
    for slot in slots:
        if now_epoch < _slot_epoch(day, slot):
            continue
        existing = observation_for_slot(day, slot, root=root)
        already_attempted = existing.get("requested_at_kst") is not None
        if already_attempted:
            continue
        captured.append(
            capture_slot(day=day, slot=slot, root=root, now_fn=now_fn, capture=capture, window_sec=window_sec)
        )

    close_slot = slots[-1]
    if now_epoch >= _slot_epoch(day, close_slot) + max(0, int(closeout_grace_sec)):
        current = observation_for_slot(day, close_slot, root=root)
        avail = str(current.get("availability") or "")
        if avail not in _COMPLETE_STATES and avail not in ("CORRUPT_STATE", "ATTEMPT_INCOMPLETE") and not bool(
            current.get("closeout_requeried")
        ):
            captured.append(
                closeout_requery_if_missing(
                    day=day, slot=close_slot, root=root, now_fn=now_fn, capture=capture,
                    window_sec=closeout_window_sec, min_ready_grace_sec=closeout_grace_sec,
                )
            )
    return captured


__all__ = [
    "DEFAULT_CLOSEOUT_WINDOW_SEC",
    "DEFAULT_OBSERVATION_ROOT",
    "DEFAULT_PRIMARY_WINDOW_SEC",
    "DEFAULT_SLOTS",
    "ManifestCorruptError",
    "SCHEMA_VERSION",
    "capture_q10_index_snapshot",
    "capture_slot",
    "closeout_requery_if_missing",
    "default_indices",
    "load_observations",
    "observation_for_slot",
    "run_due_slots",
]
