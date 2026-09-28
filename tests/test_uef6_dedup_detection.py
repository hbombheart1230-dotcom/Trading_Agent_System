"""UEF-6A Population Dedup Detection tests.

All tests use directly-constructed ``EpisodeRecord`` fixtures (via the
frozen canonical ``build_episode_record()`` builder) or an isolated
``tmp_path`` filesystem fixture -- never the live-growing repository -- so
they are strictly deterministic.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from libs.reporting.evaluation.canonical.contracts import ExecutionMode, ObservationType
from libs.reporting.evaluation.canonical.identity import DuplicateRelation
from libs.reporting.evaluation.canonical.record import EpisodeRecord, build_episode_record
from libs.reporting.evaluation.uef6.loader import UEF6LoaderError, load_episodes_jsonl, parse_episodes_jsonl
from libs.reporting.evaluation.uef6.population_dedup import (
    UEF6AccountingInvariantError,
    UEF6IdentityContentCollisionError,
    analyze_episode_population,
)
from libs.reporting.evaluation.uef6.reporter import write_dedup_report_outputs
from libs.reporting.evaluation.uef6.run_identity import compute_uef6a_run_id, detector_implementation_digest
from libs.reporting.evaluation.uef6.run_uef6a import run_uef6a_dedup_detection, UEF52_RUN_NAMESPACE


def _ep(native_id, hypothesis_id="hyp_a", execution_mode=ExecutionMode.OBSERVATION_ONLY,
        observation_type=ObservationType.CANDIDATE, symbol="005930", trading_date="2026-01-01",
        evaluator_version="", **kwargs) -> EpisodeRecord:
    return build_episode_record(
        source_namespace="uef6_test", hypothesis_id=hypothesis_id, observation_type=observation_type,
        execution_mode=execution_mode, trading_date=trading_date, symbol=symbol, native_id=native_id,
        evaluator_version=evaluator_version, **kwargs,
    )


def _mutate(ep: EpisodeRecord, **overrides) -> EpisodeRecord:
    """Returns a byte-for-byte identical copy of `ep` (same identity),
    optionally with one field's VALUE changed (e.g. metadata) -- used to
    construct a genuine content collision without changing identity."""

    payload = ep.to_dict()
    payload.update(overrides)
    return EpisodeRecord.from_dict(payload)


# ---------------------------------------------------------------------------
# A. Single record
# ---------------------------------------------------------------------------


def test_a_single_record():
    report = analyze_episode_population([_ep("EV1")])
    assert report.raw_row_count == 1
    assert report.unique_canonical_event_count == 1
    assert report.unique_evaluation_subject_count == 1
    assert report.unique_evaluation_record_count == 1
    assert report.duplicate_group_count == 0
    assert report.duplicate_excess_row_count == 0


# ---------------------------------------------------------------------------
# B. Exact repeated record x2
# ---------------------------------------------------------------------------


def test_b_exact_repeated_record_x2():
    ep = _ep("EV1")
    report = analyze_episode_population([ep, ep])
    assert report.raw_row_count == 2
    assert report.unique_canonical_event_count == 1
    assert report.unique_evaluation_subject_count == 1
    assert report.unique_evaluation_record_count == 1
    assert report.duplicate_group_count == 1
    group = report.duplicate_groups[0]
    assert group.relation == DuplicateRelation.ACCIDENTAL_DUPLICATE.value
    assert group.occurrence_count == 2
    assert group.duplicate_excess_count == 1
    assert report.relation_counts[DuplicateRelation.ACCIDENTAL_DUPLICATE.value] >= 1


# ---------------------------------------------------------------------------
# C. Exact repeated record x3
# ---------------------------------------------------------------------------


def test_c_exact_repeated_record_x3():
    ep = _ep("EV1")
    report = analyze_episode_population([ep, ep, ep])
    group = report.duplicate_groups[0]
    assert group.occurrence_count == 3
    assert group.duplicate_excess_count == 2  # NOT 3
    assert report.duplicate_excess_row_count == 2


# ---------------------------------------------------------------------------
# D. Same record id, different body -> FAIL CLOSED
# ---------------------------------------------------------------------------


def test_d_identity_content_collision_fails_closed():
    ep_a = _ep("EV1")
    ep_b = _mutate(ep_a, metadata={"tampered": True})
    with pytest.raises(UEF6IdentityContentCollisionError):
        analyze_episode_population([ep_a, ep_b])


# ---------------------------------------------------------------------------
# E. Same physical event, different hypothesis -> LEGITIMATE_MULTI_HYPOTHESIS
# ---------------------------------------------------------------------------


def test_e_legitimate_multi_hypothesis():
    ep_a = _ep("EV1", hypothesis_id="hyp_a")
    ep_b = _ep("EV1", hypothesis_id="hyp_b")
    report = analyze_episode_population([ep_a, ep_b])
    assert report.unique_canonical_event_count == 1
    assert report.unique_evaluation_subject_count == 2
    assert report.unique_evaluation_record_count == 2
    assert report.duplicate_group_count == 0  # no repeated evaluation_record_id at all
    cluster = report.event_clusters[0]
    assert cluster.relation_summary[DuplicateRelation.LEGITIMATE_MULTI_HYPOTHESIS.value] == 1
    assert cluster.unique_subject_count == 2
    # both records survive -- nothing collapsed or deleted
    assert cluster.row_count == 2


# ---------------------------------------------------------------------------
# M. Evaluator-version variant (same evaluation_record_id, different
#    evaluator_version) -- NOT a duplicate group, NOT a collision.
# ---------------------------------------------------------------------------


def test_m_evaluator_version_variant_is_not_a_duplicate_group():
    ep_v1 = _ep("EV1", evaluator_version="v1")
    ep_v2 = _ep("EV1", evaluator_version="v2")
    # same evaluation_record_id by construction (evaluator_version is not
    # an input to evaluation_record_id())
    assert ep_v1.identity.evaluation_record_id == ep_v2.identity.evaluation_record_id

    report = analyze_episode_population([ep_v1, ep_v2])
    assert report.raw_row_count == 2
    assert report.unique_evaluation_record_count == 1
    assert report.duplicate_group_count == 0
    assert report.duplicate_excess_row_count == 0
    cluster = report.event_clusters[0]
    assert cluster.relation_summary[DuplicateRelation.SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION.value] == 1
    assert DuplicateRelation.ACCIDENTAL_DUPLICATE.value not in cluster.relation_summary


# ---------------------------------------------------------------------------
# N. Mixed: exact duplicate (same version) + evaluator-version variant
# ---------------------------------------------------------------------------


def test_n_mixed_exact_duplicate_and_evaluator_variant():
    row1 = _ep("EV1", evaluator_version="v1")
    row2 = _ep("EV1", evaluator_version="v1")  # exact repeat of row1
    row3 = _mutate(_ep("EV1", evaluator_version="v2"), metadata={"note": "v2 body differs"})

    report = analyze_episode_population([row1, row2, row3])
    assert report.raw_row_count == 3
    assert report.unique_evaluation_record_count == 1
    assert report.duplicate_group_count == 1
    assert report.duplicate_excess_row_count == 1  # NOT 2

    group = report.duplicate_groups[0]
    assert group.occurrence_count == 2
    assert group.duplicate_excess_count == 1
    assert group.relation == DuplicateRelation.ACCIDENTAL_DUPLICATE.value

    cluster = report.event_clusters[0]
    # row1<->row2: ACCIDENTAL_DUPLICATE; row1<->row3 and row2<->row3: SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION
    assert cluster.relation_summary[DuplicateRelation.ACCIDENTAL_DUPLICATE.value] == 1
    assert cluster.relation_summary[DuplicateRelation.SAME_SUBJECT_DIFFERENT_EVALUATOR_VERSION.value] == 2


# ---------------------------------------------------------------------------
# O. Same evaluator_version, different semantic body -> still fail closed
# ---------------------------------------------------------------------------


def test_o_same_evaluator_version_different_body_fails_closed():
    ep_a = _ep("EV1", evaluator_version="v1")
    ep_b = _mutate(_ep("EV1", evaluator_version="v1"), metadata={"tampered": True})
    with pytest.raises(UEF6IdentityContentCollisionError):
        analyze_episode_population([ep_a, ep_b])


# ---------------------------------------------------------------------------
# F. Same subject, different execution mode
# ---------------------------------------------------------------------------


def test_f_same_subject_different_execution_mode():
    ep_a = _ep("EV1", execution_mode=ExecutionMode.OBSERVATION_ONLY)
    ep_b = _ep("EV1", execution_mode=ExecutionMode.SHADOW)
    report = analyze_episode_population([ep_a, ep_b])
    assert report.unique_evaluation_subject_count == 1
    assert report.unique_evaluation_record_count == 2
    cluster = report.event_clusters[0]
    assert cluster.relation_summary[DuplicateRelation.SAME_SUBJECT_DIFFERENT_EXECUTION_MODE.value] == 1
    # never collapsed into ACCIDENTAL_DUPLICATE
    assert DuplicateRelation.ACCIDENTAL_DUPLICATE.value not in cluster.relation_summary


# ---------------------------------------------------------------------------
# G. Different canonical event -- never a same-event duplicate candidate
# ---------------------------------------------------------------------------


def test_g_different_canonical_event_not_compared():
    ep_a = _ep("EV1")
    ep_b = _ep("EV2")
    report = analyze_episode_population([ep_a, ep_b])
    assert report.unique_canonical_event_count == 2
    assert report.event_cluster_count == 2
    for cluster in report.event_clusters:
        assert cluster.row_count == 1
        assert cluster.relation_summary == {}  # no pair ever compared


# ---------------------------------------------------------------------------
# H. Same cross_program_link_key but different event -> not duplicate
# ---------------------------------------------------------------------------


def test_h_cross_program_link_key_is_never_authority():
    from libs.reporting.evaluation.canonical.identity import cross_program_link_key

    link = cross_program_link_key(trading_date="2026-01-01", symbol="005930", context_label="OPENING_WINDOW")
    ep_a_dict = _ep("EV1").to_dict()
    ep_a_dict["identity"]["cross_program_link_key"] = link
    ep_b_dict = _ep("EV2").to_dict()
    ep_b_dict["identity"]["cross_program_link_key"] = link
    ep_a = EpisodeRecord.from_dict(ep_a_dict)
    ep_b = EpisodeRecord.from_dict(ep_b_dict)

    report = analyze_episode_population([ep_a, ep_b])
    assert report.unique_canonical_event_count == 2  # distinct events, despite sharing the link key
    assert report.duplicate_group_count == 0
    for cluster in report.event_clusters:
        assert cluster.relation_summary == {}


# ---------------------------------------------------------------------------
# I. Permuted input -> identical serialized semantic result
# ---------------------------------------------------------------------------


def test_i_order_determinism():
    episodes = [
        _ep("EV1", hypothesis_id="hyp_a"),
        _ep("EV1", hypothesis_id="hyp_b"),
        _ep("EV2"),
        _ep("EV2"),
        _ep("EV3", execution_mode=ExecutionMode.SHADOW),
    ]
    base_report = analyze_episode_population(episodes)
    base_serialized = json.dumps(base_report.summary_dict(), sort_keys=True)
    base_clusters = [c.to_dict() for c in base_report.event_clusters]
    base_groups = [g.to_dict() for g in base_report.duplicate_groups]

    rng = random.Random(1234)
    for _ in range(5):
        shuffled = list(episodes)
        rng.shuffle(shuffled)
        report = analyze_episode_population(shuffled)
        assert json.dumps(report.summary_dict(), sort_keys=True) == base_serialized
        assert [c.to_dict() for c in report.event_clusters] == base_clusters
        assert [g.to_dict() for g in report.duplicate_groups] == base_groups


# ---------------------------------------------------------------------------
# P / Q / R / S. Order-Independent Run Identity Fix: filesystem run id must
# bind the order-independent population_semantic_digest, never the raw
# episodes.jsonl byte hash.
# ---------------------------------------------------------------------------


def _write_episodes_jsonl(repo_root: Path, run_id: str, episodes: list) -> Path:
    run_dir = repo_root / UEF52_RUN_NAMESPACE / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / "episodes.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for ep in episodes:
            fh.write(json.dumps(ep.to_dict(), sort_keys=True) + "\n")
    return path


def test_p_row_order_only_permutation_preserves_run_id(tmp_path: Path):
    """Regression P: the SAME canonical episodes, written in a DIFFERENT
    JSONL row order. Raw byte hash is allowed to (and does) differ; the
    population semantic digest, run id, and semantic report must be
    identical."""

    run_id = "UEF5RUN_TESTRUN"
    a_ep, b_ep, c_ep = _ep("EV1", hypothesis_id="hyp_a"), _ep("EV1", hypothesis_id="hyp_b"), _ep("EV2")

    _write_episodes_jsonl(tmp_path, run_id, [a_ep, b_ep, c_ep])
    forward = run_uef6a_dedup_detection(tmp_path, run_id)

    _write_episodes_jsonl(tmp_path, run_id, [c_ep, a_ep, b_ep])  # permuted row order
    permuted = run_uef6a_dedup_detection(tmp_path, run_id)

    assert forward.raw_episodes_content_sha256 != permuted.raw_episodes_content_sha256
    assert forward.population_semantic_digest == permuted.population_semantic_digest
    assert forward.uef6a_run_id == permuted.uef6a_run_id
    assert forward.report.summary_dict() == permuted.report.summary_dict()
    assert [c.to_dict() for c in forward.report.event_clusters] == [c.to_dict() for c in permuted.report.event_clusters]
    assert [g.to_dict() for g in forward.report.duplicate_groups] == [g.to_dict() for g in permuted.report.duplicate_groups]


def test_q_episode_semantic_mutation_changes_run_id(tmp_path: Path):
    """Regression Q: a valid semantic field change (still a fully valid,
    identity-consistent EpisodeRecord) -> semantic digest and run id both
    change."""

    run_id = "UEF5RUN_TESTRUN"
    ep = _ep("EV1")
    _write_episodes_jsonl(tmp_path, run_id, [ep])
    before = run_uef6a_dedup_detection(tmp_path, run_id)

    mutated = _mutate(ep, metadata={"note": "a genuine semantic change, identity untouched"})
    _write_episodes_jsonl(tmp_path, run_id, [mutated])
    after = run_uef6a_dedup_detection(tmp_path, run_id)

    assert before.population_semantic_digest != after.population_semantic_digest
    assert before.uef6a_run_id != after.uef6a_run_id


def test_r_multiplicity_mutation_changes_run_id(tmp_path: Path):
    """Regression R: [A, B] vs [A, B, B] -- multiplicity is semantic input;
    the extra occurrence must change the semantic digest and run id."""

    run_id = "UEF5RUN_TESTRUN"
    a_ep, b_ep = _ep("EV1"), _ep("EV2")

    _write_episodes_jsonl(tmp_path, run_id, [a_ep, b_ep])
    before = run_uef6a_dedup_detection(tmp_path, run_id)

    _write_episodes_jsonl(tmp_path, run_id, [a_ep, b_ep, b_ep])
    after = run_uef6a_dedup_detection(tmp_path, run_id)

    assert before.population_semantic_digest != after.population_semantic_digest
    assert before.uef6a_run_id != after.uef6a_run_id
    assert before.raw_episodes_content_sha256 != after.raw_episodes_content_sha256


def test_s_repeat_identical_filesystem_run_is_deterministic(tmp_path: Path):
    """Regression S: same file bytes, same implementation -> same
    population_semantic_digest, same run id, same semantic outputs.
    generated_at (non-semantic) is deliberately excluded from this
    comparison."""

    run_id = "UEF5RUN_TESTRUN"
    _write_episodes_jsonl(tmp_path, run_id, [_ep("EV1"), _ep("EV1", hypothesis_id="hyp_b")])
    a = run_uef6a_dedup_detection(tmp_path, run_id)
    b = run_uef6a_dedup_detection(tmp_path, run_id)

    assert a.population_semantic_digest == b.population_semantic_digest
    assert a.uef6a_run_id == b.uef6a_run_id
    assert a.report.summary_dict() == b.report.summary_dict()

    out_a = write_dedup_report_outputs(tmp_path, a.uef6a_run_id, a.report, a.input_manifest())
    summary_a = json.loads((out_a / "dedup_summary.json").read_text(encoding="utf-8"))
    # a second write (e.g. a later re-run) overwrites the same run-id
    # directory; generated_at may differ -- excluded from the semantic comparison
    out_b = write_dedup_report_outputs(tmp_path, b.uef6a_run_id, b.report, b.input_manifest())
    summary_b = json.loads((out_b / "dedup_summary.json").read_text(encoding="utf-8"))
    summary_a.pop("generated_at")
    summary_b.pop("generated_at")
    assert summary_a == summary_b


def test_k_implementation_digest_mutation_changes_run_id(tmp_path: Path, monkeypatch):
    # Direct unit-level proof: two different implementation digests, same
    # everything else, produce different run ids.
    run_id_a = compute_uef6a_run_id("UEF5RUN_X", "abc123", "IMPL_DIGEST_ONE")
    run_id_b = compute_uef6a_run_id("UEF5RUN_X", "abc123", "IMPL_DIGEST_TWO")
    assert run_id_a != run_id_b

    # End-to-end proof through the real orchestrator: monkeypatch the
    # implementation-digest function it actually calls, run before/after.
    run_id = "UEF5RUN_TESTRUN"
    _write_episodes_jsonl(tmp_path, run_id, [_ep("EV1")])
    before = run_uef6a_dedup_detection(tmp_path, run_id)

    import libs.reporting.evaluation.uef6.run_uef6a as run_uef6a_mod
    monkeypatch.setattr(run_uef6a_mod, "detector_implementation_digest", lambda: "DIFFERENT_IMPLEMENTATION_DIGEST")
    after = run_uef6a_dedup_detection(tmp_path, run_id)

    assert before.uef6a_run_id != after.uef6a_run_id
    assert before.detector_implementation_digest != after.detector_implementation_digest


# (repeat-run determinism is covered by test_s_repeat_identical_filesystem_run_is_deterministic above)


# ---------------------------------------------------------------------------
# L. Malformed canonical identity -> loader rejects
# ---------------------------------------------------------------------------


def test_l_malformed_identity_rejected_by_loader():
    ep = _ep("EV1")
    payload = ep.to_dict()
    payload["identity"]["evaluation_record_id"] = "REC_0000000000000000000000"  # tampered, won't recompute-match
    raw_bytes = (json.dumps(payload) + "\n").encode("utf-8")
    with pytest.raises(UEF6LoaderError):
        parse_episodes_jsonl(raw_bytes)


def test_l_malformed_json_rejected_by_loader():
    raw_bytes = b'{"not": "valid json"' + b"\n"  # truncated JSON
    with pytest.raises(UEF6LoaderError):
        parse_episodes_jsonl(raw_bytes)


def test_loader_accepts_well_formed_episodes(tmp_path: Path):
    ep = _ep("EV1")
    path = tmp_path / "episodes.jsonl"
    path.write_text(json.dumps(ep.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    episodes, content_sha256 = load_episodes_jsonl(path)
    assert len(episodes) == 1
    assert episodes[0].identity.evaluation_record_id == ep.identity.evaluation_record_id
    assert len(content_sha256) == 64


# ---------------------------------------------------------------------------
# Accounting invariants
# ---------------------------------------------------------------------------


def test_accounting_invariants_hold_on_mixed_population():
    episodes = [
        _ep("EV1", hypothesis_id="hyp_a"),
        _ep("EV1", hypothesis_id="hyp_a"),  # exact repeat
        _ep("EV1", hypothesis_id="hyp_b"),  # multi-hypothesis
        _ep("EV2"),
        _ep("EV2", execution_mode=ExecutionMode.SHADOW),  # same subject, diff mode
        _ep("EV3"),
    ]
    report = analyze_episode_population(episodes)
    assert sum(c.row_count for c in report.event_clusters) == report.raw_row_count == 6
    assert report.unique_canonical_event_count == len({e.identity.event.canonical_event_id for e in episodes}) == 3
    assert report.unique_evaluation_subject_count == len({e.identity.evaluation_subject_id for e in episodes})
    assert report.unique_evaluation_record_count == len({e.identity.evaluation_record_id for e in episodes})
    assert report.duplicate_excess_row_count == report.raw_row_count - report.unique_evaluation_record_count


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------


def test_write_outputs_produces_all_artifacts(tmp_path: Path):
    run_id = "UEF5RUN_TESTRUN"
    _write_episodes_jsonl(tmp_path, run_id, [_ep("EV1"), _ep("EV1", hypothesis_id="hyp_b")])
    result = run_uef6a_dedup_detection(tmp_path, run_id)
    out_dir = write_dedup_report_outputs(tmp_path, result.uef6a_run_id, result.report, result.input_manifest())
    assert (out_dir / "dedup_summary.json").is_file()
    assert (out_dir / "event_clusters.jsonl").is_file()
    assert (out_dir / "duplicate_groups.jsonl").is_file()
    assert (out_dir / "input_manifest.json").is_file()
    assert (out_dir / "dedup_summary.md").is_file()

    summary = json.loads((out_dir / "dedup_summary.json").read_text(encoding="utf-8"))
    assert summary["raw_row_count"] == 2
    manifest = json.loads((out_dir / "input_manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_uef52_run_id"] == run_id
    assert manifest["raw_episodes_content_sha256"] == result.raw_episodes_content_sha256
    assert manifest["population_semantic_digest"] == result.population_semantic_digest
