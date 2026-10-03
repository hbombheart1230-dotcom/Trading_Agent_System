"""UEF-5.1 FILE-LEVEL ARTIFACT COVERAGE manifest.

THIS IS NOT COMPLETE HISTORICAL CLEAN-EVIDENCE COVERAGE. It inspects a bounded
set of artifact families, file by file. It does not scan events.jsonl,
quant-shadow record streams, Q9 windows, evaluation-daily rows, per-trade
artifacts or other record-level sources; those are disclosed explicitly in
`record_level_not_scanned`, and every discovered-but-not-parsed file is counted
in its own bucket (oversize / parse failure / unsupported format) so nothing
disappears from the denominator.

Per file: discover -> parse -> build descriptor (+ internal record descriptors)
-> run the positive verifier(s) of every matched candidate domain -> resolve.
A file is CLEAN only with positive proof and no file- or record-level negative
rule. Registry classification and UEF adapter eligibility are reported side by
side and stay independent.

Read-only and deterministic (sorted discovery, repo-relative posix paths, no
timestamps or absolute paths, canonical JSON). Computes no performance metric.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from . import clean_evidence_rules as rules
from .clean_evidence_registry import (
    EvidenceRegistry,
    EvidenceStatus,
    PositiveAuditResult,
    canonical_json,
    make_descriptor,
    matching_domains,
    resolve_evidence_status,
)

COVERAGE_SCHEMA_VERSION = "uef5_1_clean_evidence_coverage.v2"
COVERAGE_KIND = "UEF-5.1 FILE-LEVEL ARTIFACT COVERAGE"
DEFAULT_MAX_PARSE_BYTES = 64 * 1024 * 1024
_ISO_DATE_IN_PATH = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MARKER_KEYS = ("run_id", "decision_id")
_UNCLASSIFIED_SAMPLE = 10
_DAY_VALIDITY_GLOB = "reports/evaluation/daily/*/q9_day_validity.json"


@dataclass(frozen=True)
class FamilySpec:
    label: str
    family_key: str
    globs: tuple[str, ...]
    intended_for_uef5: bool
    adapter_key: str
    schema_include: tuple[str, ...] = ()
    schema_exclude: tuple[str, ...] = ()
    group: Optional[str] = None  # roll-up label, e.g. "Opening Shadow"
    record_lists: tuple[str, ...] = ()  # payload keys holding internal record lists
    record_date_keys: tuple[str, ...] = ()


_BSH = "reports/evaluation/baseline_samsung_hynix"
_BTC = "reports/evaluation/baseline_btc_woori_tech"

DEFAULT_FAMILIES: tuple[FamilySpec, ...] = (
    # ---- UEF-5 intended families ----
    FamilySpec("Q10 Semiconductor", rules.F_Q10_SEMI,
               (f"{_BSH}/*/baseline_samsung_hynix_forward_returns.json",), True, rules.F_Q10_SEMI,
               record_lists=("rows",)),
    FamilySpec("Q12 Calc1", rules.F_Q12_CALC1,
               (f"{_BTC}/*/baseline_btc_woori_forward_returns.json",), True, rules.F_Q12_CALC1,
               record_lists=("rows",)),
    FamilySpec("Q12 Calc2", rules.F_Q12_CALC2,
               (f"{_BTC}/*/q12_btc_woori_hypothesis_validation.json",), True, rules.F_Q12_CALC2),
    FamilySpec("Opening Shadow 1A", rules.F_OPENING_1A,
               ("reports/evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_forward.json",),
               True, rules.F_OPENING_1A, group="Opening Shadow",
               record_lists=("rows",), record_date_keys=("trigger_day", "initial_day")),
    FamilySpec("Opening Shadow 1B/1C", rules.F_OPENING_1BC,
               ("reports/evaluation/offline_alpha/opening_rank1_longitudinal/opening_rank1_longitudinal.json",),
               True, rules.F_OPENING_1BC, group="Opening Shadow",
               record_lists=("stage_rows", "events", "universe_paths"), record_date_keys=("day",)),
    FamilySpec("Q10 Index", rules.F_Q10_INDEX,
               (f"{_BSH}/*/q10_forward_validation/q10_actual_market_reactions.json",
                f"{_BSH}/*/q10_forward_validation/q10_expected_vs_actual.json",
                f"{_BSH}/*/q10_forward_validation/q10_shadow_entry_comparison.json"),
               True, rules.F_Q10_INDEX, record_lists=("rows",)),
    FamilySpec("Q11 v2", rules.F_Q11,
               ("reports/evaluation/opportunity_engine_shadow/*/opportunity_engine_virtual_trades.json",),
               True, rules.F_Q11, schema_include=(rules.Q11_V2_SCHEMA,), record_lists=("trades",)),
    # ---- currently BLOCKED families (reported, recompute NOT enabled) ----
    FamilySpec("Q9", rules.F_Q9,
               ("reports/dev/analysis/post_exit_shadow_recap/*/post_exit_shadow_recap.json",),
               False, rules.F_Q9, record_lists=("trades",)),
    FamilySpec("Q11 v1", rules.F_Q11,
               ("reports/evaluation/opportunity_engine_shadow/*/opportunity_engine_virtual_trades.json",),
               False, "q11_v1", schema_exclude=(rules.Q11_V2_SCHEMA,), record_lists=("trades",)),
    FamilySpec("Q12 Calc3", rules.F_Q12_CALC3, (f"{_BTC}/vnext/**/*",), False, rules.F_Q12_CALC3),
    FamilySpec("Q18", "q18", (), False, "q18"),
    FamilySpec("rank1_feature_mart", "rank1_feature_mart",
               ("reports/evaluation/feature_mart/opening_rank1/**/*",), False, "rank1_feature_mart"),
)

# Sources this file-level coverage does NOT inspect. Disclosed so that the
# manifest can never be misread as complete historical coverage.
RECORD_LEVEL_NOT_SCANNED: tuple[dict[str, Any], ...] = (
    {"source_id": "events_jsonl", "path_patterns": ["data/logs/events.jsonl"],
     "reason": "append-only record stream; record-level rules exist but the stream is not scanned here"},
    {"source_id": "quant_shadow_candidates", "path_patterns": ["data/logs/quant_shadow_candidates/**"],
     "reason": "per-candidate record files; not enumerated"},
    {"source_id": "q9_decision_windows", "path_patterns": ["reports/operator_summary/daily/*/q9_decision_windows.json"],
     "reason": "cleaned in place by a heuristic detector; window records not scanned"},
    {"source_id": "evaluation_daily_rows", "path_patterns": ["reports/evaluation/daily/**"],
     "reason": "per-day evaluation rows; only q9_day_validity.json is read (for the structural rule)"},
    {"source_id": "per_trade_artifacts", "path_patterns": ["reports/trades/**", "reports/evaluation/trades/**"],
     "reason": "per-trade lifecycle/evaluation artifacts; not enumerated"},
    {"source_id": "evidence_ledger", "path_patterns": ["data/evidence_ledger/events.jsonl"],
     "reason": "record stream with known unaudited pytest leak window"},
    {"source_id": "controlled_mock_lane_ledgers", "path_patterns": ["data/logs/controlled_mock_lanes/**"],
     "reason": "lane ledgers; not enumerated"},
    {"source_id": "canonical_run_artifacts", "path_patterns": ["reports/canonical/**"],
     "reason": "per-run canonical artifacts; not enumerated"},
    {"source_id": "root_b_jsonl", "path_patterns": ["b.jsonl"],
     "reason": "unaudited suspected pytest leak file"},
    {"source_id": "other_reports_and_data", "path_patterns": ["reports/**", "data/**"],
     "reason": "everything not matched by a FamilySpec glob is outside this coverage"},
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _walk_markers(node: Any, acc: dict[str, set[str]]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _MARKER_KEYS and isinstance(value, str) and value:
                acc.setdefault(key, set()).add(value)
            _walk_markers(value, acc)
    elif isinstance(node, list):
        for item in node:
            _walk_markers(item, acc)


def _discover(repo_root: Path, spec: FamilySpec) -> list[str]:
    found: set[str] = set()
    for pattern in spec.globs:
        for path in repo_root.glob(pattern):
            if path.is_file():
                found.add(path.relative_to(repo_root).as_posix())
    return sorted(found)


def _spec_accepts(spec: FamilySpec, schema: Optional[str]) -> bool:
    if spec.schema_include and schema not in spec.schema_include:
        return False
    if spec.schema_exclude and schema in spec.schema_exclude:
        return False
    return True


def _record_descriptors(spec: FamilySpec, rel: str, payload: Any, file_date: Optional[str]) -> list:
    """Internal record descriptors so a file can never whitelist an internal
    record that matches a record-level negative rule."""
    out = []
    if not isinstance(payload, dict):
        return out
    for key in spec.record_lists:
        rows = payload.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            date = file_date
            for dk in spec.record_date_keys:
                v = row.get(dk)
                if isinstance(v, str) and _ISO_DATE.match(v):
                    date = v
                    break
            markers: dict[str, list[str]] = {}
            native: dict[str, list[str]] = {}
            for k, v in row.items():
                if not isinstance(v, str) or not v:
                    continue
                if k == "run_id":
                    markers.setdefault("run_id", []).append(v)
                elif k.endswith("decision_id"):
                    markers.setdefault("decision_id", []).append(v)
                    native.setdefault("decision_id", []).append(v)
                elif k == "symbol":
                    markers.setdefault("symbol", []).append(v)
                elif k in ("trade_id",):
                    native.setdefault(k, []).append(v)
            out.append(
                make_descriptor(
                    family=spec.family_key, path=rel, trading_date=date, record_type=key,
                    markers=markers, native_ids=native,
                )
            )
    return out


def _load_payload(path: Path, max_bytes: int) -> tuple[str, Any]:
    """-> (state, payload): state in {"ok","oversize","parse_failed","unsupported_format"}."""
    if path.suffix.lower() != ".json":
        return "unsupported_format", None
    try:
        if path.stat().st_size > max_bytes:
            return "oversize", None
        return "ok", json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "parse_failed", None


def load_repo_day_validity(repo_root: Path) -> dict[str, Any]:
    """Read every persisted q9_day_validity.json and derive the structural
    forward-coverage-invalid days (registry authority input)."""
    repo_root = Path(repo_root)
    payloads: list[tuple[str, Any]] = []
    for path in sorted(repo_root.glob(_DAY_VALIDITY_GLOB)):
        rel = path.relative_to(repo_root).as_posix()
        try:
            payloads.append((rel, json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            payloads.append((rel, None))
    days, rejected = rules.forward_coverage_invalid_days(payloads)
    other: dict[str, int] = {}
    for _, p in payloads:
        if isinstance(p, dict) and isinstance(p.get("blockers"), list):
            for b in p["blockers"]:
                if (
                    isinstance(b, dict) and b.get("invalidates_day") is True
                    and b.get("code") not in rules.FORWARD_COVERAGE_BLOCKER_CODES
                ):
                    other[str(b.get("code"))] = other.get(str(b.get("code")), 0) + 1
    return {
        "invalid_days": days,
        "rejected": rejected,
        "payload_count": len(payloads),
        "other_invalidating_blocker_days": dict(sorted(other.items())),
    }


def build_repo_registry(repo_root: Path) -> tuple[EvidenceRegistry, dict[str, Any]]:
    dv = load_repo_day_validity(repo_root)
    return rules.build_default_registry(dv["invalid_days"]), dv


def build_descriptor(repo_root: Path, spec: FamilySpec, rel: str, *, max_parse_bytes: int = DEFAULT_MAX_PARSE_BYTES):
    """Back-compat single-descriptor builder (no records/verifiers)."""
    state, payload = _load_payload(Path(repo_root) / rel, max_parse_bytes)
    return _file_descriptor(spec, rel, payload)[0]


def _file_descriptor(spec: FamilySpec, rel: str, payload: Any):
    markers: dict[str, set[str]] = {}
    schema = program = None
    if payload is not None:
        _walk_markers(payload, markers)
        if isinstance(payload, dict):
            s = payload.get("schema_version")
            schema = s if isinstance(s, str) else None
            pr = payload.get("evaluation_program_id") or payload.get("program_id") or payload.get("program")
            program = pr if isinstance(pr, str) else None
    m = _ISO_DATE_IN_PATH.search(rel)
    file_date = m.group(1) if m else None
    desc = make_descriptor(
        family=spec.family_key, path=rel, schema_version=schema, program_id=program,
        trading_date=file_date, markers={k: v for k, v in markers.items()},
    )
    return desc, file_date


def _run_verifiers(
    repo_root: Path, registry: EvidenceRegistry, desc, payload: Any, file_date: Optional[str],
    invalid_days: frozenset,
) -> list[PositiveAuditResult]:
    audits: list[PositiveAuditResult] = []
    domains = matching_domains(desc, registry)
    if not domains:
        return audits
    parent = (Path(repo_root) / desc.path).parent

    def load_sibling(name: str) -> Any:
        try:
            return json.loads((parent / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    ctx = rules.VerificationContext(trading_date=file_date, invalid_forward_days=invalid_days, load_sibling=load_sibling)
    seen: set[str] = set()
    for dom in domains:
        vid = dom.verifier_id
        if vid is None or vid in seen:
            continue
        seen.add(vid)
        verifier: Optional[Callable[[Any, Any], PositiveAuditResult]] = rules.VERIFIERS.get(vid)
        if verifier is not None:
            audits.append(verifier(payload, ctx))
    return audits


def build_coverage_manifest(
    repo_root: Path,
    registry: Optional[EvidenceRegistry] = None,
    families: Iterable[FamilySpec] = DEFAULT_FAMILIES,
    *,
    max_parse_bytes: int = DEFAULT_MAX_PARSE_BYTES,
    day_validity: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root)
    if registry is None:
        registry, dv = build_repo_registry(repo_root)
    else:
        dv = day_validity if day_validity is not None else load_repo_day_validity(repo_root)
    invalid_days = frozenset(dv["invalid_days"])

    rows: list[dict[str, Any]] = []
    totals = {"discovered": 0, "classified": 0, "skipped_oversize": 0, "parse_failed": 0,
              "unsupported_format": 0, "unclassified": 0}
    for spec in families:
        counts = {s.value: 0 for s in EvidenceStatus}
        invalid_fields: dict[str, int] = {}
        reasons: dict[str, int] = {}
        failed_checks: dict[str, int] = {}
        unclassified: list[str] = []
        acct = {"discovered": 0, "classified": 0, "skipped_oversize": 0, "parse_failed": 0, "unsupported_format": 0}
        for rel in _discover(repo_root, spec):
            state, payload = _load_payload(repo_root / rel, max_parse_bytes)
            desc, file_date = _file_descriptor(spec, rel, payload if state == "ok" else None)
            if state == "ok" and not _spec_accepts(spec, desc.schema_version):
                continue
            acct["discovered"] += 1
            if state == "ok":
                acct["classified"] += 1
            else:
                acct[{"oversize": "skipped_oversize"}.get(state, state)] += 1
            records = _record_descriptors(spec, rel, payload, file_date) if state == "ok" else []
            audits = _run_verifiers(repo_root, registry, desc, payload, file_date, invalid_days) if state == "ok" else []
            res = resolve_evidence_status(desc, registry, audits=audits, records=records)
            counts[res.status.value] += 1
            for f in res.invalid_fields:
                invalid_fields[f] = invalid_fields.get(f, 0) + 1
            for r in res.reason_codes:
                reasons[r] = reasons.get(r, 0) + 1
            for chk in res.failed_checks:
                failed_checks[chk] = failed_checks.get(chk, 0) + 1
            if res.status is EvidenceStatus.NO_RULE:
                unclassified.append(rel)
        eligibility = rules.ADAPTER_ELIGIBILITY[spec.adapter_key]
        for k in ("discovered", "classified", "skipped_oversize", "parse_failed", "unsupported_format"):
            totals[k] += acct[k]
        totals["unclassified"] += counts["NO_RULE"]
        rows.append(
            {
                "label": spec.label,
                "group": spec.group,
                "family_key": spec.family_key,
                "intended_for_uef5": spec.intended_for_uef5,
                "accounting": {**acct, "unclassified": counts["NO_RULE"]},
                "registry_classification": {
                    "total_discovered": acct["discovered"],
                    "CLEAN": counts["CLEAN"],
                    "QUARANTINED": counts["QUARANTINED"],
                    "FIELD_INVALID": counts["FIELD_INVALID"],
                    "REVIEW_REQUIRED": counts["REVIEW_REQUIRED"],
                    "unclassified": counts["NO_RULE"],
                    "invalid_field_counts": dict(sorted(invalid_fields.items())),
                    "reason_code_counts": dict(sorted(reasons.items())),
                    "failed_check_counts": dict(sorted(failed_checks.items())),
                    "unclassified_sample": sorted(unclassified)[:_UNCLASSIFIED_SAMPLE],
                },
                "uef_adapter_eligibility": {
                    "adapter_status": eligibility["adapter_status"],
                    "authority": eligibility["authority"],
                },
            }
        )
    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "coverage_kind": COVERAGE_KIND,
        "complete_historical_coverage": False,
        "scope_disclosure": (
            "File-level artifact coverage of the listed families only. It is NOT complete historical "
            "clean-evidence coverage: record-level sources are not scanned (see record_level_not_scanned), "
            "and files that could not be parsed are counted in their own buckets."
        ),
        "registry_version": registry.registry_version,
        "registry_digest": registry.digest(),
        "structural_forward_coverage": {
            "contract": "libs/reporting/evaluation/day_validity.py::MIN_FORWARD_COVERAGE via persisted q9_day_validity.json invalidates_day",
            "day_validity_payloads_read": dv["payload_count"],
            "invalid_days": {d: list(c) for d, c in dv["invalid_days"].items()},
            "payloads_rejected": list(dv["rejected"]),
            "other_invalidating_blocker_days_not_encoded": dv["other_invalidating_blocker_days"],
        },
        "note": (
            "registry_classification is evidence cleanliness; uef_adapter_eligibility is a separate, "
            "independent fact. A CLEAN artifact for a BLOCKED adapter is NOT eligible for recompute."
        ),
        "families": rows,
        "totals": totals,
        "record_level_not_scanned": [dict(item) for item in RECORD_LEVEL_NOT_SCANNED],
    }


def coverage_manifest_json(manifest: dict[str, Any]) -> str:
    return canonical_json(manifest)


__all__ = [
    "COVERAGE_KIND",
    "COVERAGE_SCHEMA_VERSION",
    "DEFAULT_FAMILIES",
    "FamilySpec",
    "RECORD_LEVEL_NOT_SCANNED",
    "build_coverage_manifest",
    "build_descriptor",
    "build_repo_registry",
    "coverage_manifest_json",
    "load_repo_day_validity",
]
