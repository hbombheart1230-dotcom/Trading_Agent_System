# tests/test_build_api_catalog.py
import json
from pathlib import Path


def test_api_catalog_built_and_unique_ids():
    path = Path("data/specs/api_catalog.jsonl")
    assert path.exists(), "api_catalog.jsonl not found"

    ids = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        api_id = rec["api_id"]
        assert api_id not in ids, f"Duplicated api_id: {api_id}"
        ids.add(api_id)


def test_api_catalog_has_minimal_fields():
    path = Path("data/specs/api_catalog.jsonl")
    rec = json.loads(path.read_text(encoding="utf-8").splitlines()[0])

    for key in ("api_id", "title", "method", "path", "_flags"):
        assert key in rec
