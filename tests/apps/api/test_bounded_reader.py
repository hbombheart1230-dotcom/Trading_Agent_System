from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.infrastructure.bounded_reader import (
    BoundedReadError,
    read_bytes_bounded,
    read_json_bounded,
)


def test_bounded_reader_rejects_large_file(tmp_path: Path) -> None:
    source = tmp_path / "large.json"
    source.write_bytes(b"x" * 17)

    with pytest.raises(BoundedReadError, match="exceeds read limit"):
        read_bytes_bounded(source, max_bytes=16)


def test_json_reader_accepts_utf8(tmp_path: Path) -> None:
    source = tmp_path / "valid.json"
    source.write_text('{"symbol_name":"삼성전자"}', encoding="utf-8")

    assert read_json_bounded(source, max_bytes=1024) == {
        "symbol_name": "삼성전자"
    }


def test_json_reader_rejects_malformed_json(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text('{"broken":', encoding="utf-8")

    with pytest.raises(BoundedReadError, match="invalid UTF-8 JSON"):
        read_json_bounded(source, max_bytes=1024)
