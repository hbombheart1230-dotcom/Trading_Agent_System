"""UEF-6A filesystem input loader.

File loading lives OUTSIDE the pure classifier (``population_dedup.py``).
Uses the canonical ``EpisodeRecord.from_dict()`` deserializer so full
identity validation (recomputed ``evaluation_subject_id``/
``evaluation_record_id``, ``EventRef`` hash consistency, every other
``__post_init__`` check the frozen record contract already enforces) runs
on every line -- this loader never hand-parses only the few fields UEF-6A
happens to use. Malformed or identity-inconsistent input fails closed
(the underlying ``CanonicalRecordValidationError``/``ValueError`` is
wrapped in a UEF-6-local error type but never swallowed).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterator, Sequence

from libs.reporting.evaluation.canonical import EpisodeRecord


class UEF6LoaderError(Exception):
    """Raised when episodes.jsonl input cannot be loaded as valid, identity-consistent EpisodeRecords."""


def parse_episodes_jsonl(raw_bytes: bytes) -> list:
    """Pure parse: raw file bytes -> list[EpisodeRecord]. No filesystem access.

    Fails closed: the first malformed or identity-inconsistent line raises
    ``UEF6LoaderError`` (wrapping the underlying canonical validation
    error) -- never silently skipped, never partially accepted."""

    text = raw_bytes.decode("utf-8")
    episodes = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise UEF6LoaderError(f"episodes.jsonl line {line_number}: not valid JSON: {exc}") from exc
        try:
            episode = EpisodeRecord.from_dict(payload)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad: ANY canonical validation failure fails closed
            raise UEF6LoaderError(
                f"episodes.jsonl line {line_number}: failed canonical EpisodeRecord validation "
                f"({type(exc).__name__}: {exc})"
            ) from exc
        episodes.append(episode)
    return episodes


def load_episodes_jsonl(path: Path) -> tuple:
    """Loads one ``episodes.jsonl`` file. Returns (episodes, content_sha256)
    -- the raw-byte hash is computed BEFORE any parsing, so it identifies
    the exact input bytes regardless of how parsing succeeds/fails."""

    raw_bytes = Path(path).read_bytes()
    content_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    episodes = parse_episodes_jsonl(raw_bytes)
    return episodes, content_sha256
