from __future__ import annotations

import json
from typing import Any, Dict, List

import libs.reporting.trade_report_ai as mod


class _Route:
    def __init__(self, model: str) -> None:
        self.model = model


class _RetrySuccessRouter:
    def __init__(self) -> None:
        self.client = object()
        self.calls = 0

    @staticmethod
    def from_env() -> "_RetrySuccessRouter":
        return _RetrySuccessRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        self.calls += 1
        if self.calls == 1:
            return "not-json"
        return (
            '{"executive_summary":{"headline":"HOLD 000660","action":"HOLD","symbol":"000660","confidence":"high","summary":"ok"},'
            '"market_context_at_entry":{"summary":"context","bullets":["vix noted"]},'
            '"why_this_symbol_was_chosen":{"summary":"rank #1","bullets":["top value"]},'
            '"entry_decision":{"summary":"entry","bullets":[]},'
            '"holding_monitoring_story":{"summary":"hold","bullets":[]},'
            '"exit_decision":{"summary":"open trade","bullets":[]},'
            '"execution_quality":{"summary":"execution","bullets":[]},'
            '"scanner_filters":{"summary":"filters","bullets":[]},'
            '"guard_approval_result":{"summary":"guard","bullets":[]},'
            '"reporter_evaluation":{"summary":"reporter","status":"pending","grade":"N/A","bullets":[]},'
            '"errors_weaknesses_improvement_points":{"summary":"none","bullets":[]},'
            '"full_timeline":[{"event":"entry","ts":"2026-03-18T00:00:00+00:00","description":"entry"}],'
            '"final_operator_conclusion":{"summary":"hold","current_action":"HOLD","watch_next":["watch"],"thesis_invalidation":["stop"]}}'
        )


class _AlwaysEmptyRouter:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_AlwaysEmptyRouter":
        return _AlwaysEmptyRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return ""


class _TruncatedOuterJsonRouter:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_TruncatedOuterJsonRouter":
        return _TruncatedOuterJsonRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return (
            'prefix {"executive_summary":{"headline":"HOLD 000660","action":"HOLD","symbol":"000660","confidence":"high","summary":"ok"}}'
            ', "market_context_at_entry": {"summary":"cut off before outer object closes"'
        )


class _MissingKeysRouter:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_MissingKeysRouter":
        return _MissingKeysRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return json.dumps(
            {
                "executive_summary": {"headline": "HOLD 000660", "action": "HOLD", "symbol": "000660", "confidence": "high", "summary": "ok"},
                "market_context_at_entry": {"summary": "context", "bullets": ["vix noted"]},
            }
        )


class _ProseThenCompleteJsonRouter:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_ProseThenCompleteJsonRouter":
        return _ProseThenCompleteJsonRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return (
            "I will now return the final JSON object only. "
            '{"executive_summary":{"headline":"HOLD 000660","action":"HOLD","symbol":"000660","confidence":"high","summary":"ok"},'
            '"market_context_at_entry":{"summary":"context","bullets":["vix noted"]},'
            '"why_this_symbol_was_chosen":{"summary":"rank #1","bullets":["top value"]},'
            '"entry_decision":{"summary":"entry","bullets":[]},'
            '"holding_monitoring_story":{"summary":"hold","bullets":[]},'
            '"exit_decision":{"summary":"open trade","bullets":[]},'
            '"execution_quality":{"summary":"execution","bullets":[]},'
            '"scanner_filters":{"summary":"filters","bullets":[]},'
            '"guard_approval_result":{"summary":"guard","bullets":[]},'
            '"reporter_evaluation":{"summary":"reporter","status":"pending","grade":"N/A","bullets":[]},'
            '"errors_weaknesses_improvement_points":{"summary":"none","bullets":[]},'
            '"full_timeline":[{"event":"entry","ts":"2026-03-18T00:00:00+00:00","description":"entry"}],'
            '"final_operator_conclusion":{"summary":"hold","current_action":"HOLD","watch_next":["watch"],"thesis_invalidation":["stop"]}}'
        )


class _CapturePolicyRouter:
    last_policies: List[Dict[str, Any]] = []

    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_CapturePolicyRouter":
        _CapturePolicyRouter.last_policies = []
        return _CapturePolicyRouter()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(str((policy or {}).get("model") or "openrouter/free"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        _CapturePolicyRouter.last_policies.append(dict(policy or {}))
        return (
            '{"executive_summary":{"headline":"HOLD 000660","action":"HOLD","symbol":"000660","confidence":"high","summary":"ok"},'
            '"market_context_at_entry":{"summary":"context","bullets":["vix noted"]},'
            '"why_this_symbol_was_chosen":{"summary":"rank #1","bullets":["top value"]},'
            '"entry_decision":{"summary":"entry","bullets":[]},'
            '"holding_monitoring_story":{"summary":"hold","bullets":[]},'
            '"exit_decision":{"summary":"open trade","bullets":[]},'
            '"execution_quality":{"summary":"execution","bullets":[]},'
            '"scanner_filters":{"summary":"filters","bullets":[]},'
            '"guard_approval_result":{"summary":"guard","bullets":[]},'
            '"reporter_evaluation":{"summary":"reporter","status":"pending","grade":"N/A","bullets":[]},'
            '"errors_weaknesses_improvement_points":{"summary":"none","bullets":[]},'
            '"full_timeline":[{"event":"entry","ts":"2026-03-18T00:00:00+00:00","description":"entry"}],'
            '"final_operator_conclusion":{"summary":"hold","current_action":"HOLD","watch_next":["watch"],"thesis_invalidation":["stop"]}}'
        )


def _story_input() -> Dict[str, Any]:
    return {
        "trade_id": "TRD_20260318_000660_01",
        "story_id": "TRD_20260318_000660_01",
        "run_id": "run-1",
        "day": "2026-03-18",
        "symbol": "000660",
        "action": "HOLD",
        "status": "open",
        "story_type": "simulation",
        "execution_mode_label": "simulation",
        "monitor_reason_human": {"posture": "HOLD"},
    }


def test_ai_trade_report_retries_before_success(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _RetrySuccessRouter)

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "ok"
    assert artifact["retry_count"] == 1
    assert len(artifact["attempts"]) == 2
    assert artifact["model"] == "openrouter/free"


def test_ai_trade_report_writes_failure_state_after_retries(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _AlwaysEmptyRouter)
    monkeypatch.setenv("TRADE_REPORT_AI_RETRY_MAX", "2")

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "empty_response"
    assert report["failure"]["status"] == "empty_response"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "empty_response"
    assert artifact["retry_count"] == 2
    assert report["executive_summary"]["headline"].startswith("AI trade report failed")


def test_ai_trade_report_truncated_outer_json_is_not_treated_as_ok(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _TruncatedOuterJsonRouter)

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "salvaged"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "salvaged"
    assert artifact["parse_mode"] == "partial"
    assert "executive_summary" in artifact["required_keys_present"]
    assert "market_context_at_entry" in artifact["required_keys_missing"]
    assert artifact["completeness_score"] < 1.0
    assert artifact["used_fallback_sections"]


def test_ai_trade_report_missing_required_keys_is_downgraded(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _MissingKeysRouter)

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "salvaged"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "salvaged"
    assert artifact["parse_mode"] == "full"
    assert "executive_summary" in artifact["required_keys_present"]
    assert "entry_decision" in artifact["required_keys_missing"]
    assert artifact["completeness_score"] < 1.0


def test_ai_trade_report_complete_json_with_leading_prose_is_repaired(monkeypatch):
    monkeypatch.setattr(mod, "LLMRouter", _ProseThenCompleteJsonRouter)

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "repaired"
    artifact = report["llm_response_artifact"]
    assert artifact["status"] == "repaired"
    assert artifact["parse_mode"] == "partial"
    assert artifact["required_keys_missing"] == []
    assert artifact["completeness_score"] == 1.0


def test_ai_trade_report_messages_use_compact_projection() -> None:
    story_input = _story_input()
    story_input["entry_summary"] = {"run_id": "run-entry", "reason_human": "entry reason"}
    story_input["holding_summary"] = {
        "run_ids": [f"run-{i}" for i in range(40)],
        "holding_events": [{"event": "hold", "description": "x" * 200} for _ in range(20)],
        "posture_history": [{"ts": f"2026-03-18T00:00:{i:02d}+00:00", "posture": "HOLD", "reason": "monitor"} for i in range(12)],
        "monitor_updates": [f"update-{i}-" + ("y" * 200) for i in range(30)],
    }
    story_input["timeline"] = [
        {"ts": f"2026-03-18T00:00:{i:02d}+00:00", "event": "monitor", "description": "z" * 200}
        for i in range(20)
    ]
    story_input["market_context_human"] = {"summary": "market context", "bullets": ["vix", "news", "macro"]}
    story_input["scanner_reason_human"] = {"summary": "scanner context", "runner_ups": ["A", "B", "C"]}

    messages = mod._build_messages(story_input)
    user_prompt = str(messages[1]["content"])

    assert "holding_event_count" in user_prompt
    assert "recent_monitor_updates" in user_prompt
    assert "holding_events" not in user_prompt
    assert "\"posture_history\"" not in user_prompt
    assert len(user_prompt) < 12000


def test_ai_trade_report_messages_use_clean_json_only_instructions() -> None:
    messages = mod._build_messages(_story_input())
    system_prompt = str(messages[0]["content"])
    user_prompt = str(messages[1]["content"])

    assert "Return exactly one JSON object only." in system_prompt
    assert "Do not invent numbers" in system_prompt
    assert "All human-readable values must be written in Korean." in system_prompt
    assert "strategist -> scanner -> monitor -> supervisor -> executor -> reporter" in user_prompt
    assert "Return only this JSON template with values filled in" in user_prompt
    assert "Do not copy English source sentences into the final JSON." in user_prompt


def test_ai_trade_report_repair_messages_do_not_reinject_non_json_reasoning() -> None:
    messages = mod._build_repair_messages(_story_input(), "First, the user says I should output JSON.")
    system_prompt = str(messages[0]["content"])
    user_prompt = str(messages[1]["content"])

    assert "do not think aloud" in system_prompt.lower()
    assert "[previous response was non-JSON reasoning or invalid text; ignore it]" in user_prompt
    assert "First, the user says" not in user_prompt
    assert "Never describe your plan" in system_prompt


def test_ai_trade_report_sparse_repair_messages_use_shorter_contract() -> None:
    story_input = _story_input()
    story_input["timeline"] = [
        {"ts": f"2026-03-18T00:00:{i:02d}+00:00", "event": "holding", "description": "monitor hold"}
        for i in range(12)
    ]

    regular = mod._build_repair_messages(story_input, "not-json", sparse=False)
    sparse = mod._build_repair_messages(story_input, "not-json", sparse=True)
    regular_prompt = str(regular[1]["content"])
    sparse_prompt = str(sparse[1]["content"])

    assert "final repair pass" in sparse_prompt
    assert "full_timeline to at most 8 rows" in sparse_prompt
    assert len(sparse_prompt) < len(regular_prompt)


def test_ai_trade_report_language_meta_flags_mostly_english_sections() -> None:
    candidate = {
        "executive_summary": {
            "headline": "Trade closed after quick exit",
            "summary": "Current lifecycle status is closed.",
        },
        "market_context_at_entry": {
            "summary": "Market regime was neutral with a defensive playbook.",
            "bullets": ["Global sentiment score: -0.22", "VIX level: 25.09"],
        },
        "final_operator_conclusion": {
            "summary": "Review the monitor trigger and reporter linkage.",
            "watch_next": ["Monitor trigger changes", "Macro/news shifts"],
            "thesis_invalidation": ["negative macro regime shift"],
        },
    }

    meta = mod._trade_report_language_meta(candidate)

    assert meta["requires_korean_repair"] is True
    assert meta["language_english_like_count"] >= 6


def test_ai_trade_report_repair_messages_can_enforce_korean() -> None:
    messages = mod._build_repair_messages(_story_input(), "not-json", sparse=True, enforce_korean=True)
    system_prompt = str(messages[0]["content"])
    user_prompt = str(messages[1]["content"])

    assert "All human-readable values must be written in Korean." in system_prompt
    assert "Translate any remaining English human-readable text into Korean" in user_prompt
    assert "watch_next" in user_prompt


def test_ai_trade_report_compact_input_is_smaller_than_full_story() -> None:
    story_input = _story_input()
    story_input["holding_summary"] = {
        "run_ids": [f"run-{i}" for i in range(40)],
        "holding_events": [{"event": "hold", "description": "x" * 200} for _ in range(30)],
        "monitor_updates": [f"update-{i}-" + ("y" * 200) for i in range(20)],
    }
    story_input["timeline"] = [
        {"ts": f"2026-03-18T00:00:{i:02d}+00:00", "event": "monitor", "description": "z" * 200}
        for i in range(20)
    ]

    compact_input = mod.build_ai_trade_report_compact_input(story_input)
    full_len = len(json.dumps(story_input, ensure_ascii=False))
    compact_len = len(json.dumps(compact_input, ensure_ascii=False))

    assert compact_len < full_len
    assert "holding_events" not in json.dumps(compact_input, ensure_ascii=False)


def test_ai_trade_report_uses_openrouter_default_max_tokens_when_role_value_missing(monkeypatch) -> None:
    monkeypatch.setattr(mod, "LLMRouter", _CapturePolicyRouter)
    monkeypatch.delenv("TRADE_REPORT_AI_MAX_TOKENS", raising=False)
    monkeypatch.setenv("OPENROUTER_DEFAULT_MAX_TOKENS", "4096")

    report = mod.build_ai_trade_report(_story_input(), enabled=True, model="free")

    assert report["generation"]["status"] == "ok"
    assert _CapturePolicyRouter.last_policies
    assert int(_CapturePolicyRouter.last_policies[0]["max_tokens"]) == 4096
    assert _CapturePolicyRouter.last_policies[0]["plugins"] == [{"id": "response-healing"}]


def test_ai_trade_report_fallback_preserves_structured_market_context_fields() -> None:
    story_input = _story_input()
    story_input["market_context_human"] = {
        "regime": "risk_off",
        "market_sentiment": "bearish",
        "playbook": "defensive",
        "themes": ["defensive_assets"],
        "global_sentiment_score": -0.22,
        "vix_level": 25.09,
        "stress_flags": ["elevated_vix"],
        "summary": "risk-off market context",
        "bullets": ["Market regime: risk_off"],
    }
    story_input["scanner_reason_human"] = {
        "selected_symbol": "000660",
        "selected_rank": 1,
        "universe_size": 5,
        "ranking_basis": ["trading value", "theme alignment"],
        "summary": "scanner selected rank #1",
        "bullets": ["Universe scanned: 5", "Selected rank: #1"],
    }

    report = mod._merge_trade_report_candidate(
        story_input,
        {},
        status="salvaged",
        mode="ai",
        model="openrouter/free",
        reason="partial",
    )

    assert report["generation"]["status"] == "salvaged"
    assert report["report_generation"]["status"] == "salvaged"
    assert report["market_context_at_entry"]["regime"] == "risk_off"
    assert report["market_context_at_entry"]["global_sentiment_score"] == -0.22
    assert report["market_context_at_entry"]["vix_level"] == 25.09
    assert report["why_this_symbol_was_chosen"]["selected_rank"] == 1
    assert report["why_this_symbol_was_chosen"]["universe_size"] == 5
