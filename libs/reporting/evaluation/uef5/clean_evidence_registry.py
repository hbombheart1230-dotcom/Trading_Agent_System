"""UEF-5.1 Clean Evidence Registry -- contract + deterministic resolver.

Authority boundary for UEF-5 historical recompute: says which legacy
evidence is CLEAN / QUARANTINED / FIELD_INVALID / REVIEW_REQUIRED, and which
is simply outside any declared clean domain (NO_RULE). It does NOT compute
any performance metric, and it does NOT decide adapter eligibility (that is
a separate fact, see clean_evidence_rules.ADAPTER_ELIGIBILITY).

Design (see docs/research/uef5_1_clean_evidence_registry.md):
  * Declarative data (clean_evidence_rules.py) + this small deterministic
    resolver. No historical exclusion is hidden in `if date == ...` code.
  * CLEAN requires POSITIVE PROOF (UEF-5.1 FIX1). A CleanDomain is only a
    CANDIDATE ("eligible to be positively audited"); matching one never makes
    evidence CLEAN. CLEAN needs: matched domain + a PositiveAuditResult from
    the domain's declared PositiveCleanVerifier with outcome PROVEN_CLEAN and
    every domain `required_checks` passed + no negative rule (file- OR
    record-level). Matched but unproven -> REVIEW_REQUIRED; unmatched ->
    NO_RULE. Governing principle: false REVIEW_REQUIRED beats false CLEAN.
  * Negative rules carry structured scope; free text is explanatory only.
  * Total severity order QUARANTINED > REVIEW_REQUIRED > FIELD_INVALID >
    CLEAN > NO_RULE; resolution is a max over matches plus set unions, so
    rule order never changes the result.
  * Duplicate ids, identical-scope rules, or otherwise conflicting rules
    make registry construction FAIL (RegistryContractError) instead of
    silently picking one.

Stdlib only; imports nothing from production runtime, broker or the frozen
UEF core. Canonical serialization mirrors the UEF-1 identity pattern
(sort_keys, compact separators, ensure_ascii) re-implemented locally so the
frozen identity module is not touched.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from typing import Any, Iterable, Mapping, Optional, Sequence

SCHEMA_VERSION = "uef5_1_clean_evidence_registry.v1"

_RULE_ID_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class RegistryContractError(ValueError):
    """Registry or scope/descriptor contract violation (fail closed)."""


class EvidenceStatus(str, Enum):
    CLEAN = "CLEAN"
    QUARANTINED = "QUARANTINED"
    FIELD_INVALID = "FIELD_INVALID"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NO_RULE = "NO_RULE"


class ReasonCode(str, Enum):
    TEST_SYNTHETIC_CONTAMINATION = "TEST_SYNTHETIC_CONTAMINATION"
    STALE_MOCK_FILL = "STALE_MOCK_FILL"
    INSUFFICIENT_SOURCE_COVERAGE = "INSUFFICIENT_SOURCE_COVERAGE"
    INVALID_SCANNER_ATTRIBUTION = "INVALID_SCANNER_ATTRIBUTION"
    INVALID_TIMING_ALIGNMENT = "INVALID_TIMING_ALIGNMENT"
    UNRESOLVED_SOURCE_PROVENANCE = "UNRESOLVED_SOURCE_PROVENANCE"
    SOURCE_FIELD_NOT_PERSISTED = "SOURCE_FIELD_NOT_PERSISTED"
    POSITIVE_CLEAN_NOT_PROVEN = "POSITIVE_CLEAN_NOT_PROVEN"
    POSITIVE_CLEAN_CONTRADICTED = "POSITIVE_CLEAN_CONTRADICTED"


# Total severity order used for merging matched rules (higher wins).
_SEVERITY = {
    EvidenceStatus.NO_RULE: 0,
    EvidenceStatus.CLEAN: 1,
    EvidenceStatus.FIELD_INVALID: 2,
    EvidenceStatus.REVIEW_REQUIRED: 3,
    EvidenceStatus.QUARANTINED: 4,
}
_NEGATIVE_STATUSES = (
    EvidenceStatus.QUARANTINED,
    EvidenceStatus.REVIEW_REQUIRED,
    EvidenceStatus.FIELD_INVALID,
)


# ---------------------------------------------------------------------------
# canonical serialization / hashing (local re-implementation of the UEF-1
# identity pattern; the frozen identity module is not imported or edited)
# ---------------------------------------------------------------------------

def canonical_json(value: Any) -> str:
    def _default(obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        raise TypeError(f"not canonically serializable: {type(obj)!r}")

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=_default)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# glob -> regex (deterministic, filesystem-independent): `**` crosses '/',
# `*` and `?` do not.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=None)
def _glob_regex(pattern: str) -> "re.Pattern[str]":
    out: list[str] = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "*":
            if pattern[i : i + 2] == "**":
                out.append(".*")
                i += 2
                continue
            out.append("[^/]*")
        elif ch == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(ch))
        i += 1
    return re.compile("".join(out))


def path_matches_glob(path: str, pattern: str) -> bool:
    return _glob_regex(pattern).fullmatch(path) is not None


def _valid_iso_date(value: str) -> bool:
    if not _ISO_DATE_RE.match(value):
        return False
    y, m, d = int(value[:4]), int(value[5:7]), int(value[8:])
    return 1 <= m <= 12 and 1 <= d <= 31 and y >= 1970


def _norm_multi(mapping: Optional[Mapping[str, Iterable[str]]]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    if not mapping:
        return ()
    out = []
    for key in sorted(mapping):
        values = tuple(sorted({str(v) for v in mapping[key]}))
        if not values:
            raise RegistryContractError(f"scope dimension {key!r} has no values")
        out.append((str(key), values))
    return tuple(out)


# ---------------------------------------------------------------------------
# Positive clean authority (UEF-5.1 FIX1)
# ---------------------------------------------------------------------------

class PositiveOutcome(str, Enum):
    PROVEN_CLEAN = "PROVEN_CLEAN"  # every declared check passed from persisted evidence
    NOT_PROVEN = "NOT_PROVEN"  # proof could not be established (missing field, no verifier, ...)
    INVALID = "INVALID"  # persisted evidence positively contradicts cleanliness


@dataclass(frozen=True)
class PositiveAuditResult:
    """Outcome of one PositiveCleanVerifier run. `verifier_id` is a stable
    identifier (never prose); logic uses only structured fields."""

    verifier_id: str
    outcome: PositiveOutcome
    passed_checks: tuple[str, ...] = ()
    failed_checks: tuple[str, ...] = ()
    record_count: int = 0

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "verifier_id": self.verifier_id,
            "outcome": self.outcome.value,
            "passed_checks": sorted(self.passed_checks),
            "failed_checks": sorted(self.failed_checks),
            "record_count": self.record_count,
        }


# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Scope:
    """Minimum-necessary narrowing. Every specified dimension must match
    (AND); within a multi-valued dimension any value may match (OR)."""

    family: Optional[str] = None
    source_namespace: Optional[str] = None
    path_globs: tuple[str, ...] = ()
    schema_versions: tuple[str, ...] = ()
    program_ids: tuple[str, ...] = ()
    date_start: Optional[str] = None  # inclusive ISO date
    date_end: Optional[str] = None  # inclusive ISO date
    record_type: Optional[str] = None
    native_ids: tuple[tuple[str, tuple[str, ...]], ...] = ()  # kind -> regex fullmatch
    markers_equals: tuple[tuple[str, tuple[str, ...]], ...] = ()  # field -> exact values
    marker_patterns: tuple[tuple[str, tuple[str, ...]], ...] = ()  # field -> regex fullmatch

    def __post_init__(self) -> None:
        if not (
            self.family
            or self.source_namespace
            or self.path_globs
            or self.schema_versions
            or self.program_ids
            or self.date_start
            or self.date_end
            or self.record_type
            or self.native_ids
            or self.markers_equals
            or self.marker_patterns
        ):
            raise RegistryContractError("empty scope would match everything")
        for label, value in (("date_start", self.date_start), ("date_end", self.date_end)):
            if value is not None and not _valid_iso_date(value):
                raise RegistryContractError(f"{label} must be ISO YYYY-MM-DD: {value!r}")
        if self.date_start and self.date_end and self.date_start > self.date_end:
            raise RegistryContractError("date_start after date_end")
        for pattern in self.path_globs:
            if not pattern or "\\" in pattern or pattern.startswith("/"):
                raise RegistryContractError(f"path glob must be relative posix: {pattern!r}")
        for _, patterns in self.native_ids + self.marker_patterns:
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise RegistryContractError(f"invalid regex {pattern!r}: {exc}") from exc

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "source_namespace": self.source_namespace,
            "path_globs": list(self.path_globs),
            "schema_versions": list(self.schema_versions),
            "program_ids": list(self.program_ids),
            "date_start": self.date_start,
            "date_end": self.date_end,
            "record_type": self.record_type,
            "native_ids": [[k, list(v)] for k, v in self.native_ids],
            "markers_equals": [[k, list(v)] for k, v in self.markers_equals],
            "marker_patterns": [[k, list(v)] for k, v in self.marker_patterns],
        }


def make_scope(
    *,
    family: Optional[str] = None,
    source_namespace: Optional[str] = None,
    path_globs: Iterable[str] = (),
    schema_versions: Iterable[str] = (),
    program_ids: Iterable[str] = (),
    date_start: Optional[str] = None,
    date_end: Optional[str] = None,
    record_type: Optional[str] = None,
    native_ids: Optional[Mapping[str, Iterable[str]]] = None,
    markers_equals: Optional[Mapping[str, Iterable[str]]] = None,
    marker_patterns: Optional[Mapping[str, Iterable[str]]] = None,
) -> Scope:
    return Scope(
        family=family,
        source_namespace=source_namespace,
        path_globs=tuple(sorted(set(path_globs))),
        schema_versions=tuple(sorted(set(schema_versions))),
        program_ids=tuple(sorted(set(program_ids))),
        date_start=date_start,
        date_end=date_end,
        record_type=record_type,
        native_ids=_norm_multi(native_ids),
        markers_equals=_norm_multi(markers_equals),
        marker_patterns=_norm_multi(marker_patterns),
    )


# ---------------------------------------------------------------------------
# Evidence descriptor (what a consumer asks about)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceDescriptor:
    family: str
    path: str  # repo-relative posix path
    schema_version: Optional[str] = None
    program_id: Optional[str] = None
    trading_date: Optional[str] = None
    record_type: Optional[str] = None
    source_namespace: Optional[str] = None
    native_ids: tuple[tuple[str, str], ...] = ()  # (kind, value)
    markers: tuple[tuple[str, tuple[str, ...]], ...] = ()  # field -> observed values

    def __post_init__(self) -> None:
        if not self.family:
            raise RegistryContractError("descriptor family required")
        if not self.path or "\\" in self.path or self.path.startswith("/") or re.match(r"^[A-Za-z]:", self.path):
            raise RegistryContractError(f"descriptor path must be relative posix: {self.path!r}")
        if self.trading_date is not None and not _valid_iso_date(self.trading_date):
            raise RegistryContractError(f"descriptor trading_date must be ISO: {self.trading_date!r}")


def make_descriptor(
    *,
    family: str,
    path: str,
    schema_version: Optional[str] = None,
    program_id: Optional[str] = None,
    trading_date: Optional[str] = None,
    record_type: Optional[str] = None,
    source_namespace: Optional[str] = None,
    native_ids: Optional[Mapping[str, Iterable[str]]] = None,
    markers: Optional[Mapping[str, Iterable[str]]] = None,
) -> EvidenceDescriptor:
    ids: list[tuple[str, str]] = []
    for kind in sorted(native_ids or {}):
        for value in sorted({str(v) for v in native_ids[kind]}):  # type: ignore[index]
            ids.append((str(kind), value))
    marker_items = []
    for key in sorted(markers or {}):
        values = tuple(sorted({str(v) for v in markers[key]}))  # type: ignore[index]
        marker_items.append((str(key), values))
    return EvidenceDescriptor(
        family=family,
        path=path,
        schema_version=schema_version,
        program_id=program_id,
        trading_date=trading_date,
        record_type=record_type,
        source_namespace=source_namespace,
        native_ids=tuple(ids),
        markers=tuple(marker_items),
    )


def scope_matches(scope: Scope, d: EvidenceDescriptor) -> bool:
    if scope.family is not None and d.family != scope.family:
        return False
    if scope.source_namespace is not None and d.source_namespace != scope.source_namespace:
        return False
    if scope.path_globs and not any(path_matches_glob(d.path, g) for g in scope.path_globs):
        return False
    if scope.schema_versions and d.schema_version not in scope.schema_versions:
        return False
    if scope.program_ids and d.program_id not in scope.program_ids:
        return False
    if scope.date_start is not None or scope.date_end is not None:
        if d.trading_date is None:
            return False  # an undated record cannot be positively placed in a date window
        if scope.date_start is not None and d.trading_date < scope.date_start:
            return False
        if scope.date_end is not None and d.trading_date > scope.date_end:
            return False
    if scope.record_type is not None and d.record_type != scope.record_type:
        return False
    for kind, patterns in scope.native_ids:
        values = [v for k, v in d.native_ids if k == kind]
        if not any(re.fullmatch(p, v) for v in values for p in patterns):
            return False
    marker_map = dict(d.markers)
    for field, allowed in scope.markers_equals:
        if not any(v in allowed for v in marker_map.get(field, ())):
            return False
    for field, patterns in scope.marker_patterns:
        if not any(re.fullmatch(p, v) for v in marker_map.get(field, ()) for p in patterns):
            return False
    return True


# ---------------------------------------------------------------------------
# Rules / domains / registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceRule:
    rule_id: str
    status: EvidenceStatus
    reason_code: ReasonCode
    scope: Scope
    source_authority: tuple[str, ...]
    human_note: str  # explanatory only; never used by resolution logic
    invalid_fields: tuple[str, ...] = ()
    # Fields that are neither proven invalid nor provable clean (REVIEW_REQUIRED
    # at field level). Only valid alongside FIELD_INVALID (e.g. controlled-lane
    # rank fields are invalid while its P&L fields are merely unproven).
    review_fields: tuple[str, ...] = ()
    review_reason_code: Optional[ReasonCode] = None

    def __post_init__(self) -> None:
        if not _RULE_ID_RE.match(self.rule_id):
            raise RegistryContractError(f"bad rule_id {self.rule_id!r}")
        if self.status not in _NEGATIVE_STATUSES:
            raise RegistryContractError(f"{self.rule_id}: negative rules must be QUARANTINED/FIELD_INVALID/REVIEW_REQUIRED")
        if self.status is EvidenceStatus.FIELD_INVALID and not self.invalid_fields:
            raise RegistryContractError(f"{self.rule_id}: FIELD_INVALID requires invalid_fields")
        if self.status is not EvidenceStatus.FIELD_INVALID and self.invalid_fields:
            raise RegistryContractError(f"{self.rule_id}: invalid_fields only valid for FIELD_INVALID")
        if self.review_fields:
            if self.status is not EvidenceStatus.FIELD_INVALID:
                raise RegistryContractError(f"{self.rule_id}: review_fields only valid for FIELD_INVALID")
            if self.review_reason_code is None:
                raise RegistryContractError(f"{self.rule_id}: review_fields require review_reason_code")
            if set(self.review_fields) & set(self.invalid_fields):
                raise RegistryContractError(f"{self.rule_id}: a field cannot be both invalid and under review")
        elif self.review_reason_code is not None:
            raise RegistryContractError(f"{self.rule_id}: review_reason_code without review_fields")
        if not self.source_authority:
            raise RegistryContractError(f"{self.rule_id}: source_authority required")

    def identity(self) -> dict[str, Any]:
        return {
            "kind": "rule",
            "rule_id": self.rule_id,
            "status": self.status.value,
            "reason_code": self.reason_code.value,
            "scope": self.scope.to_canonical_dict(),
            "invalid_fields": sorted(self.invalid_fields),
            "review_fields": sorted(self.review_fields),
            "review_reason_code": self.review_reason_code.value if self.review_reason_code else None,
            "source_authority": sorted(self.source_authority),
            "human_note": self.human_note,
        }


@dataclass(frozen=True)
class CleanDomain:
    """CANDIDATE declaration, not a cleanliness claim. Matching a domain only
    means the evidence is eligible to be positively audited. It becomes CLEAN
    (for `fields`; empty = every field) only when the domain's
    PositiveCleanVerifier (`verifier_id`) returns PROVEN_CLEAN with every one
    of `required_checks` passed and no negative rule matches. A domain with no
    verifier can never produce CLEAN (matched -> REVIEW_REQUIRED)."""

    domain_id: str
    scope: Scope
    source_authority: tuple[str, ...]
    human_note: str
    fields: tuple[str, ...] = ()
    verifier_id: Optional[str] = None
    required_checks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not _RULE_ID_RE.match(self.domain_id):
            raise RegistryContractError(f"bad domain_id {self.domain_id!r}")
        if not self.source_authority:
            raise RegistryContractError(f"{self.domain_id}: source_authority required")
        if self.verifier_id is not None and not self.required_checks:
            raise RegistryContractError(f"{self.domain_id}: a verifier requires declared required_checks")
        if self.verifier_id is None and self.required_checks:
            raise RegistryContractError(f"{self.domain_id}: required_checks without a verifier_id")

    def identity(self) -> dict[str, Any]:
        return {
            "kind": "clean_domain",
            "domain_id": self.domain_id,
            "scope": self.scope.to_canonical_dict(),
            "fields": sorted(self.fields),
            "verifier_id": self.verifier_id,
            "required_checks": sorted(self.required_checks),
            "source_authority": sorted(self.source_authority),
            "human_note": self.human_note,
        }


@dataclass(frozen=True)
class EvidenceRegistry:
    registry_version: str
    rules: tuple[EvidenceRule, ...]
    clean_domains: tuple[CleanDomain, ...]

    def digest(self) -> str:
        return stable_digest(
            {
                "schema_version": SCHEMA_VERSION,
                "registry_version": self.registry_version,
                "rules": [r.identity() for r in self.rules],
                "clean_domains": [c.identity() for c in self.clean_domains],
            }
        )

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "registry_version": self.registry_version,
            "registry_digest": self.digest(),
            "rules": [r.identity() for r in self.rules],
            "clean_domains": [c.identity() for c in self.clean_domains],
        }

    def to_canonical_json(self) -> str:
        return canonical_json(self.to_canonical_dict())


def build_registry(
    registry_version: str,
    rules: Sequence[EvidenceRule],
    clean_domains: Sequence[CleanDomain],
) -> EvidenceRegistry:
    """Validate and freeze. Input order never matters: rules/domains are
    sorted by id. Duplicate ids, identical-scope rules (duplicate or
    conflicting) and identical-scope+fields domains raise
    RegistryContractError -- the registry refuses to exist rather than pick
    a winner."""
    ids: set[str] = set()
    for item in list(rules) + list(clean_domains):
        key = item.rule_id if isinstance(item, EvidenceRule) else item.domain_id
        if key in ids:
            raise RegistryContractError(f"duplicate id: {key}")
        ids.add(key)

    seen_rule_scope: dict[str, EvidenceRule] = {}
    for rule in rules:
        scope_key = canonical_json(rule.scope.to_canonical_dict())
        prior = seen_rule_scope.get(scope_key)
        if prior is not None:
            same = (prior.status, prior.reason_code, sorted(prior.invalid_fields), sorted(prior.review_fields)) == (
                rule.status,
                rule.reason_code,
                sorted(rule.invalid_fields),
                sorted(rule.review_fields),
            )
            kind = "duplicate" if same else "conflicting"
            raise RegistryContractError(
                f"{kind} rules with identical scope: {prior.rule_id} vs {rule.rule_id}"
            )
        seen_rule_scope[scope_key] = rule

    seen_domain: dict[str, CleanDomain] = {}
    for domain in clean_domains:
        key = canonical_json(
            {
                "scope": domain.scope.to_canonical_dict(),
                "fields": sorted(domain.fields),
                "verifier_id": domain.verifier_id,
                "required_checks": sorted(domain.required_checks),
            }
        )
        if key in seen_domain:
            raise RegistryContractError(
                f"duplicate clean domains: {seen_domain[key].domain_id} vs {domain.domain_id}"
            )
        seen_domain[key] = domain

    return EvidenceRegistry(
        registry_version=registry_version,
        rules=tuple(sorted(rules, key=lambda r: r.rule_id)),
        clean_domains=tuple(sorted(clean_domains, key=lambda c: c.domain_id)),
    )


# ---------------------------------------------------------------------------
# Resolver
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Resolution:
    status: EvidenceStatus
    evidence_level_status: EvidenceStatus  # before field-level (invalid/review) bumps
    invalid_fields: tuple[str, ...]
    review_fields: tuple[str, ...]
    reason_codes: tuple[str, ...]
    matched_rule_ids: tuple[str, ...]
    record_level_rule_ids: tuple[str, ...]  # negative rules hit by INTERNAL records
    matched_domain_ids: tuple[str, ...]  # candidate domains matched
    proven_domain_ids: tuple[str, ...]  # candidate domains positively proven
    clean_fields: tuple[str, ...]  # union over PROVEN domains only; ("*",) = all fields
    positive_verifier_ids: tuple[str, ...]
    failed_checks: tuple[str, ...]

    def field_status(self, field: str) -> EvidenceStatus:
        base = self.evidence_level_status
        if base is EvidenceStatus.QUARANTINED:
            return EvidenceStatus.QUARANTINED
        if field in self.review_fields:
            return EvidenceStatus.REVIEW_REQUIRED
        if field in self.invalid_fields:
            return EvidenceStatus.FIELD_INVALID
        if base is EvidenceStatus.REVIEW_REQUIRED:
            return EvidenceStatus.REVIEW_REQUIRED
        if base is EvidenceStatus.CLEAN and ("*" in self.clean_fields or field in self.clean_fields):
            return EvidenceStatus.CLEAN
        return EvidenceStatus.NO_RULE

    def field_usable(self, field: str) -> bool:
        """True only when `field` is positively proven CLEAN: never for
        quarantined / review / unclassified evidence, never for an invalid or
        under-review field, and only when a PROVEN domain covers it."""
        return self.field_status(field) is EvidenceStatus.CLEAN

    def to_canonical_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "evidence_level_status": self.evidence_level_status.value,
            "invalid_fields": list(self.invalid_fields),
            "review_fields": list(self.review_fields),
            "reason_codes": list(self.reason_codes),
            "matched_rule_ids": list(self.matched_rule_ids),
            "record_level_rule_ids": list(self.record_level_rule_ids),
            "matched_domain_ids": list(self.matched_domain_ids),
            "proven_domain_ids": list(self.proven_domain_ids),
            "clean_fields": list(self.clean_fields),
            "positive_verifier_ids": list(self.positive_verifier_ids),
            "failed_checks": list(self.failed_checks),
        }


def matching_domains(descriptor: EvidenceDescriptor, registry: EvidenceRegistry) -> tuple[CleanDomain, ...]:
    return tuple(c for c in registry.clean_domains if scope_matches(c.scope, descriptor))


def _domain_proof(domain: CleanDomain, audits: Mapping[str, PositiveAuditResult]) -> tuple[str, Optional[PositiveAuditResult]]:
    """-> ("PROVEN"|"NOT_PROVEN"|"CONTRADICTED", audit)."""
    if domain.verifier_id is None:
        return "NOT_PROVEN", None
    audit = audits.get(domain.verifier_id)
    if audit is None:
        return "NOT_PROVEN", None
    if audit.outcome is PositiveOutcome.INVALID:
        return "CONTRADICTED", audit
    if audit.outcome is PositiveOutcome.PROVEN_CLEAN:
        missing = set(domain.required_checks) - set(audit.passed_checks)
        if not missing and not audit.failed_checks:
            return "PROVEN", audit
        return "NOT_PROVEN", audit  # a verifier cannot skip a declared check
    return "NOT_PROVEN", audit


def resolve_evidence_status(
    descriptor: EvidenceDescriptor,
    registry: EvidenceRegistry,
    *,
    audits: Iterable[PositiveAuditResult] = (),
    records: Iterable[EvidenceDescriptor] = (),
) -> Resolution:
    """Resolve one artifact. `audits` are the caller-run PositiveCleanVerifier
    results (matched to domains by verifier_id); `records` are descriptors of
    the artifact's INTERNAL records, so a file can never whitelist an internal
    record that independently matches a QUARANTINED / REVIEW_REQUIRED rule
    (such a file is floored at REVIEW_REQUIRED, never CLEAN)."""
    audit_map = {a.verifier_id: a for a in audits}
    matched = [r for r in registry.rules if scope_matches(r.scope, descriptor)]
    domains = list(matching_domains(descriptor, registry))

    record_rules: dict[str, EvidenceRule] = {}
    record_floor = False
    for rec in records:
        for r in registry.rules:
            if scope_matches(r.scope, rec):
                record_rules[r.rule_id] = r
                if r.status in (EvidenceStatus.QUARANTINED, EvidenceStatus.REVIEW_REQUIRED):
                    record_floor = True

    matched_ids = {m.rule_id for m in matched}
    all_neg = list(matched) + [r for rid, r in record_rules.items() if rid not in matched_ids]
    evidence_negative = [r for r in matched if r.status in (EvidenceStatus.QUARANTINED, EvidenceStatus.REVIEW_REQUIRED)]

    reasons: set[str] = {r.reason_code.value for r in all_neg}
    proven: list[CleanDomain] = []
    verifier_ids: set[str] = set()
    failed: set[str] = set()
    unproven_reason: Optional[str] = None
    for dom in domains:
        outcome, audit = _domain_proof(dom, audit_map)
        if dom.verifier_id:
            verifier_ids.add(dom.verifier_id)
        if audit is not None:
            failed.update(audit.failed_checks)
            failed.update(set(dom.required_checks) - set(audit.passed_checks))
        if outcome == "PROVEN":
            proven.append(dom)
        elif outcome == "CONTRADICTED":
            unproven_reason = ReasonCode.POSITIVE_CLEAN_CONTRADICTED.value
        elif unproven_reason is None:
            unproven_reason = ReasonCode.POSITIVE_CLEAN_NOT_PROVEN.value

    if evidence_negative:
        base = max((r.status for r in evidence_negative), key=lambda st: _SEVERITY[st])
        if record_floor and _SEVERITY[base] < _SEVERITY[EvidenceStatus.REVIEW_REQUIRED]:
            base = EvidenceStatus.REVIEW_REQUIRED
    elif record_floor:
        base = EvidenceStatus.REVIEW_REQUIRED
    elif proven:
        base = EvidenceStatus.CLEAN
    elif domains:
        base = EvidenceStatus.REVIEW_REQUIRED
        reasons.add(unproven_reason or ReasonCode.POSITIVE_CLEAN_NOT_PROVEN.value)
    else:
        base = EvidenceStatus.NO_RULE

    invalid: set[str] = set()
    review: set[str] = set()
    field_level = False
    for r in all_neg:
        invalid.update(r.invalid_fields)
        if r.review_fields:
            review.update(r.review_fields)
            reasons.add(r.review_reason_code.value)  # type: ignore[union-attr]
        if r.status is EvidenceStatus.FIELD_INVALID:
            field_level = True

    status = base
    if field_level and _SEVERITY[status] < _SEVERITY[EvidenceStatus.FIELD_INVALID]:
        status = EvidenceStatus.FIELD_INVALID
    if review and _SEVERITY[status] < _SEVERITY[EvidenceStatus.REVIEW_REQUIRED]:
        status = EvidenceStatus.REVIEW_REQUIRED

    clean_fields: set[str] = set()
    for dom in proven:
        clean_fields.update(dom.fields or ("*",))

    return Resolution(
        status=status,
        evidence_level_status=base,
        invalid_fields=tuple(sorted(invalid)),
        review_fields=tuple(sorted(review)),
        reason_codes=tuple(sorted(reasons)),
        matched_rule_ids=tuple(sorted(r.rule_id for r in matched)),
        record_level_rule_ids=tuple(sorted(rid for rid in record_rules if rid not in matched_ids)),
        matched_domain_ids=tuple(sorted(d.domain_id for d in domains)),
        proven_domain_ids=tuple(sorted(d.domain_id for d in proven)),
        clean_fields=tuple(sorted(clean_fields)),
        positive_verifier_ids=tuple(sorted(verifier_ids)),
        failed_checks=tuple(sorted(failed)),
    )


__all__ = [
    "SCHEMA_VERSION",
    "CleanDomain",
    "EvidenceDescriptor",
    "EvidenceRegistry",
    "EvidenceRule",
    "EvidenceStatus",
    "ReasonCode",
    "RegistryContractError",
    "PositiveAuditResult",
    "PositiveOutcome",
    "Resolution",
    "Scope",
    "build_registry",
    "canonical_json",
    "make_descriptor",
    "make_scope",
    "matching_domains",
    "path_matches_glob",
    "resolve_evidence_status",
    "scope_matches",
    "stable_digest",
]
