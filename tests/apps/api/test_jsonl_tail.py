from __future__ import annotations

import json

from apps.api.infrastructure.jsonl_tail import read_jsonl_tail


def test_jsonl_tail_is_bounded_and_drops_partial_first_line(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    path.write_text(
        "".join(json.dumps({"index": index, "text": "x" * 40}) + "\n" for index in range(20)),
        encoding="utf-8",
    )

    result = read_jsonl_tail(path, max_bytes=300, max_rows=3)

    assert result.truncated is True
    assert [row["index"] for row in result.rows] == [17, 18, 19]
    assert result.scanned_bytes <= 300
