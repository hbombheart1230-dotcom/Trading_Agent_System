from __future__ import annotations

import json

import libs.reporting.alert_notifier as notifier


def test_m25_6_notify_none_provider_skips():
    out = notifier.notify_batch_result(
        batch_result={"ok": True, "rc": 0, "day": "2026-02-17"},
        provider="none",
        notify_on="always",
    )
    assert out["ok"] is True
    assert out["skipped"] is True
    assert out["reason"] == "provider_none"


def test_m25_6_notify_webhook_dry_run_skips_send():
    out = notifier.notify_batch_result(
        batch_result={"ok": False, "rc": 3, "day": "2026-02-17"},
        provider="webhook",
        webhook_url="https://example.invalid/webhook",
        notify_on="failure",
        dry_run=True,
    )
    assert out["ok"] is True
    assert out["skipped"] is True
    assert out["reason"] == "dry_run"


def test_m25_6_notify_webhook_success(monkeypatch):
    class _DummyResp:
        status = 200

        def getcode(self):  # type: ignore[no-untyped-def]
            return 200

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
            return False

    def _fake_urlopen(req, timeout=5):  # type: ignore[no-untyped-def]
        assert timeout == 5
        body = req.data.decode("utf-8")
        payload = json.loads(body)
        assert payload["kind"] == "m25_ops_batch"
        return _DummyResp()

    monkeypatch.setattr(notifier.urllib_request, "urlopen", _fake_urlopen)
    out = notifier.notify_batch_result(
        batch_result={"ok": False, "rc": 3, "day": "2026-02-17"},
        provider="webhook",
        webhook_url="https://example.invalid/webhook",
        notify_on="failure",
        timeout_sec=5,
        dry_run=False,
    )
    assert out["ok"] is True
    assert out["sent"] is True
    assert out["status_code"] == 200
