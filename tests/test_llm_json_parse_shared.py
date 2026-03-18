from __future__ import annotations

from libs.llm.json_response import parse_llm_json_response, required_key_metadata


def test_parse_llm_json_response_marks_full_dict_as_ok() -> None:
    result = parse_llm_json_response('{"headline":"ok","summary":"full"}')
    assert result["is_full"] is True
    assert result["is_partial"] is False
    assert result["full_object"] == {"headline": "ok", "summary": "full"}


def test_parse_llm_json_response_marks_truncated_outer_json_as_partial() -> None:
    raw = 'prefix {"headline":"partial","summary":"usable"} trailing {"broken":'
    result = parse_llm_json_response(raw)
    assert result["is_full"] is False
    assert result["is_partial"] is True
    assert result["partial_object"] == {"headline": "partial", "summary": "usable"}


def test_required_key_metadata_reports_missing_keys() -> None:
    meta = required_key_metadata({"headline": "ok"}, ["headline", "summary", "timeline"])
    assert meta["required_keys_present"] == ["headline"]
    assert meta["required_keys_missing"] == ["summary", "timeline"]
    assert meta["completeness_score"] < 1.0
