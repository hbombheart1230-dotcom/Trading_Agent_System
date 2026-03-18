from __future__ import annotations


def test_m20_3_legacy_router_import_path_is_valid():
    from libs.llm.openrouter_client import ChatMessage
    from libs.llm.router import LLMRouter, TextLLMRouter

    assert LLMRouter is not None
    assert TextLLMRouter is not None
    assert ChatMessage is not None


def test_m20_3_legacy_router_chat_builds_payload_with_new_resolver():
    from libs.llm.router import LLMRouter

    class FakeClient:
        def __init__(self) -> None:
            self.payload = None

        def chat_completions(self, payload):  # type: ignore[no-untyped-def]
            self.payload = dict(payload)
            return {"id": "resp-1", "choices": [{"message": {"content": "ok"}}]}

    client = FakeClient()
    router = LLMRouter(client=client)  # type: ignore[arg-type]

    out = router.chat(
        role="STRATEGIST",
        policy={
            "model": "anthropic/claude-3.5-sonnet",
            "temperature": 0.3,
            "max_tokens": 111,
        },
        messages=[
            {"role": "system", "content": "You are a strategist."},
            {"role": "user", "content": "Pick one symbol."},
        ],
        extra={"top_p": 0.8},
    )

    assert out["id"] == "resp-1"
    assert client.payload is not None
    assert client.payload["model"] == "anthropic/claude-3.5-sonnet"
    assert abs(float(client.payload["temperature"]) - 0.3) < 1e-9
    assert int(client.payload["max_tokens"]) == 111
    assert client.payload["messages"][0]["role"] == "system"
    assert client.payload["top_p"] == 0.8


def test_m20_3_legacy_router_passes_response_format():
    from libs.llm.router import LLMRouter

    class FakeClient:
        def __init__(self) -> None:
            self.payload = None

        def chat_completions(self, payload):  # type: ignore[no-untyped-def]
            self.payload = dict(payload)
            return {"id": "resp-1", "choices": [{"message": {"content": "{}"}}]}

    client = FakeClient()
    router = LLMRouter(client=client)  # type: ignore[arg-type]

    router.chat(
        role="STRATEGIST",
        policy={
            "model": "anthropic/claude-3.5-sonnet",
            "response_format": {"type": "json_object"},
        },
        messages=[{"role": "user", "content": "Return json"}],
    )

    assert client.payload is not None
    assert client.payload["response_format"] == {"type": "json_object"}


def test_m20_3_text_router_resolves_role_specific_auto_and_free_models(monkeypatch):
    from libs.llm.llm_router import LLMRouter

    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "free")
    monkeypatch.setenv("OPENROUTER_MODEL_OPERATOR_UI", "free")
    monkeypatch.setenv("OPENROUTER_MODEL_REPORTER_FINAL", "auto")
    monkeypatch.setenv("OPENROUTER_MODEL_DAILY_REPORT", "auto")

    router = LLMRouter(client=None)  # type: ignore[arg-type]

    assert router.resolve("operator_ui").model == "openrouter/free"
    assert router.resolve("reporter_final").model == "openrouter/auto"
    assert router.resolve("daily_report").model == "openrouter/auto"
    assert router.resolve("reporter_intraday").model == "openrouter/free"


def test_m20_3_text_router_normalizes_policy_auto_alias():
    from libs.llm.llm_router import LLMRouter

    router = LLMRouter(client=None)  # type: ignore[arg-type]
    assert router.resolve("strategist", policy={"model": "auto"}).model == "openrouter/auto"
    assert router.resolve("operator_ui", policy={"model": "free"}).model == "openrouter/free"


def test_m20_3_text_router_preserves_direct_provider_model_name():
    from libs.llm.llm_router import LLMRouter

    router = LLMRouter(client=None)  # type: ignore[arg-type]
    assert router.resolve("strategist", policy={"model": "minimax/minimax-m2.5"}).model == "minimax/minimax-m2.5"
