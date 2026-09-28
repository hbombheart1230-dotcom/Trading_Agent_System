"""UEF-6B pure episode-lineage verification.

``verify_witness_against_episode_population`` matches EVALUATED witness
member occurrences against a supplied ``EpisodeRecord`` population ONLY
via exact ``evaluation_record_id`` equality -- never symbol/date/
hypothesis/count. Reuses UEF-6A's own identity/content-collision
principle (and its exact error type) rather than reinventing it: if the
supplied episode population itself contains two ``EpisodeRecord``s
sharing one ``evaluation_record_id`` with different canonical content,
this fails closed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Sequence

from libs.reporting.evaluation.canonical import EpisodeRecord

from .lineage_model import AggregateLineageWitness, EpisodeVerificationResult
from .population_dedup import UEF6IdentityContentCollisionError


def _episode_content_digest(episode: EpisodeRecord) -> str:
    payload = json.dumps(episode.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _index_episodes_by_record_id(episodes: Sequence[EpisodeRecord]) -> dict:
    """Fail-closed index build: reuses UEF-6A's identity/content-collision
    principle -- two episodes sharing one evaluation_record_id with
    different canonical content is an integrity violation, not a harmless
    duplicate to silently resolve."""

    by_id: dict = {}
    digests: dict = {}
    for episode in episodes:
        record_id = episode.identity.evaluation_record_id
        if not record_id:
            continue
        digest = _episode_content_digest(episode)
        if record_id in digests and digests[record_id] != digest:
            raise UEF6IdentityContentCollisionError(
                f"episode population contains evaluation_record_id={record_id!r} with two distinct canonical "
                "content digests -- same claimed episode identity, different canonical content. FAIL CLOSED: "
                "never arbitrarily selecting one."
            )
        digests[record_id] = digest
        by_id[record_id] = episode
    return by_id


def verify_witness_against_episode_population(
    witness: AggregateLineageWitness,
    episodes: Sequence[EpisodeRecord],
) -> EpisodeVerificationResult:
    """Pure function: no filesystem access, no mutation of ``witness`` or
    ``episodes``. Every EVALUATED member OCCURRENCE in the witness (with
    multiplicity preserved -- a repeated evaluated member is checked once
    per occurrence, not deduplicated first) is checked against the
    supplied episode population by exact ``evaluation_record_id`` only."""

    episodes_by_id = _index_episodes_by_record_id(episodes)

    evaluated_occurrences = [m for m in witness.member_occurrences if m.state == "EVALUATED"]
    matched: list = []
    missing: list = []
    for occurrence in evaluated_occurrences:
        record_id = occurrence.evaluation_record_id
        if record_id and record_id in episodes_by_id:
            matched.append(record_id)
        else:
            missing.append(record_id)

    evaluated_member_count = len(evaluated_occurrences)
    evaluated_episode_match_count = len(matched)
    evaluated_episode_missing_count = len(missing)
    exact_evaluated_episode_membership_proven = evaluated_member_count > 0 and evaluated_episode_missing_count == 0

    return EpisodeVerificationResult(
        evaluated_member_count=evaluated_member_count,
        evaluated_episode_match_count=evaluated_episode_match_count,
        evaluated_episode_missing_count=evaluated_episode_missing_count,
        exact_evaluated_episode_membership_proven=exact_evaluated_episode_membership_proven,
        matched_evaluation_record_ids=tuple(sorted(matched)),
        missing_evaluation_record_ids=tuple(sorted(missing)),
    )
