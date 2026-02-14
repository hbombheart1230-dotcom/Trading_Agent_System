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
