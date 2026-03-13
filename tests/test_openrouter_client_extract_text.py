from __future__ import annotations

import json

from libs.llm.openrouter_client import OpenRouterClient


def test_extract_text_prefers_message_content_string():
    resp = {"choices": [{"message": {"content": '{"ok":true}'}}]}
    assert OpenRouterClient.extract_text(resp) == '{"ok":true}'


def test_extract_text_reads_structured_parsed_message():
    resp = {
        "choices": [
            {
                "message": {
                    "parsed": {
                        "market_regime": "risk_on",
                        "themes": ["semiconductor"],
                    }
                }
            }
        ]
    }
    text = OpenRouterClient.extract_text(resp)
    assert json.loads(text)["market_regime"] == "risk_on"


def test_extract_text_reads_tool_call_arguments():
    resp = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "arguments": '{"market_regime":"neutral","themes":["leaders"]}'
                            }
                        }
                    ],
                }
            }
        ]
    }
    text = OpenRouterClient.extract_text(resp)
    assert json.loads(text)["themes"] == ["leaders"]


def test_extract_text_falls_back_to_reasoning_when_content_missing():
    resp = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "reasoning": '{"market_regime":"risk_off","themes":["defensive"]}',
                }
            }
        ]
    }
    text = OpenRouterClient.extract_text(resp)
    assert json.loads(text)["market_regime"] == "risk_off"


def test_extract_text_reads_legacy_choice_text():
    resp = {"choices": [{"text": '{"market_regime":"neutral"}'}]}
    text = OpenRouterClient.extract_text(resp)
    assert json.loads(text)["market_regime"] == "neutral"
