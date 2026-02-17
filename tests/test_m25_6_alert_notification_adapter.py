from __future__ import annotations

import json

import libs.reporting.alert_notifier as notifier


class _DummyResp:
    status = 200

    def getcode(self):  # type: ignore[no-untyped-def]
        return 200

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, exc_type, exc, tb):  # type: ignore[no-untyped-def]
        return False


def _install_success_urlopen(monkeypatch):  # type: ignore[no-untyped-def]
    def _fake_urlopen(req, timeout=5):  # type: ignore[no-untyped-def]
        assert timeout == 5
        body = req.data.decode("utf-8")
        payload = json.loads(body)
        assert payload["kind"] == "m25_ops_batch"
        return _DummyResp()

    monkeypatch.setattr(notifier.urllib_request, "urlopen", _fake_urlopen)


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
    _install_success_urlopen(monkeypatch)
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


def test_m25_7_notify_dedup_suppressed(monkeypatch, tmp_path):
    _install_success_urlopen(monkeypatch)
    state_path = tmp_path / "notify_state.json"
    batch = {"ok": False, "rc": 3, "day": "2026-02-17"}

    out1 = notifier.notify_batch_result(
        batch_result=batch,
        provider="webhook",
        webhook_url="https://example.invalid/webhook",
        notify_on="failure",
        timeout_sec=5,
        state_path=str(state_path),
        dedup_window_sec=600,
        rate_limit_window_sec=600,
        max_per_window=5,
        dry_run=False,
    )
    out2 = notifier.notify_batch_result(
        batch_result=batch,
        provider="webhook",
        webhook_url="https://example.invalid/webhook",
        notify_on="failure",
        timeout_sec=5,
        state_path=str(state_path),
        dedup_window_sec=600,
        rate_limit_window_sec=600,
        max_per_window=5,
        dry_run=False,
    )

    assert out1["ok"] is True
    assert out1["sent"] is True
    assert out2["ok"] is True
    assert out2["skipped"] is True
    assert out2["reason"] == "dedup_suppressed"


def test_m25_7_notify_rate_limited(monkeypatch, tmp_path):
    _install_success_urlopen(monkeypatch)
    state_path = tmp_path / "notify_state.json"

    out1 = notifier.notify_batch_result(
        batch_result={"ok": False, "rc": 3, "day": "2026-02-17"},
        provider="webhook",
        webhook_url="https://example.invalid/webhook",
        notify_on="failure",
        timeout_sec=5,
        state_path=str(state_path),
        dedup_window_sec=0,
        rate_limit_window_sec=600,
        max_per_window=1,
        dry_run=False,
    )
    out2 = notifier.notify_batch_result(
        batch_result={"ok": False, "rc": 2, "day": "2026-02-17"},
        provider="webhook",
        webhook_url="https://example.invalid/webhook",
        notify_on="failure",
        timeout_sec=5,
        state_path=str(state_path),
        dedup_window_sec=0,
        rate_limit_window_sec=600,
        max_per_window=1,
        dry_run=False,
    )

    assert out1["ok"] is True
    assert out1["sent"] is True
    assert out2["ok"] is True
    assert out2["skipped"] is True
    assert out2["reason"] == "rate_limited"
