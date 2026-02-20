from __future__ import annotations

import json
from urllib import error as urllib_error

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


def _batch_with_portfolio_guard_alerts() -> dict:
    return {
        "ok": False,
        "rc": 3,
        "day": "2026-02-20",
        "closeout": {
            "metrics_schema": {"ok": True, "rc": 0, "failure_total": 0},
            "alert_policy": {
                "ok": False,
                "rc": 3,
                "alert_total": 3,
                "severity_total": {"warning": 3},
                "alert_codes": [
                    "execution_blocked_rate_high",
                    "portfolio_guard_blocked_ratio_high",
                    "portfolio_guard_strategy_budget_exceeded_high",
                ],
            },
            "daily_report": {"events": 10, "path_json": "reports/sample.json"},
        },
        "failures": ["alert_policy rc != 0"],
    }


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


def test_m25_8_notify_slack_webhook_success(monkeypatch):
    def _fake_urlopen(req, timeout=5):  # type: ignore[no-untyped-def]
        assert timeout == 5
        body = req.data.decode("utf-8")
        payload = json.loads(body)
        assert "text" in payload
        assert "metadata" in payload
        assert payload["metadata"]["kind"] == "m25_ops_batch"
        return _DummyResp()

    monkeypatch.setattr(notifier.urllib_request, "urlopen", _fake_urlopen)
    out = notifier.notify_batch_result(
        batch_result={"ok": False, "rc": 3, "day": "2026-02-17"},
        provider="slack_webhook",
        webhook_url="https://example.invalid/slack-hook",
        notify_on="failure",
        timeout_sec=5,
        dry_run=False,
    )
    assert out["ok"] is True
    assert out["sent"] is True
    assert out["provider"] == "slack_webhook"
    assert out["status_code"] == 200


def test_m25_9_notify_webhook_retry_after_429(monkeypatch):
    calls = {"n": 0}

    def _fake_urlopen(req, timeout=5):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib_error.HTTPError(
                url="https://example.invalid/webhook",
                code=429,
                msg="too many requests",
                hdrs=None,
                fp=None,
            )
        return _DummyResp()

    monkeypatch.setattr(notifier.urllib_request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(notifier.time, "sleep", lambda _: None)

    out = notifier.notify_batch_result(
        batch_result={"ok": False, "rc": 3, "day": "2026-02-17"},
        provider="webhook",
        webhook_url="https://example.invalid/webhook",
        notify_on="failure",
        timeout_sec=5,
        retry_max=1,
        retry_backoff_sec=0.01,
        dry_run=False,
    )
    assert calls["n"] == 2
    assert out["ok"] is True
    assert out["sent"] is True
    assert out["reason"] == "sent_after_retry"


def test_m27_8_notify_escalates_provider_on_portfolio_guard_alerts():
    out = notifier.notify_batch_result(
        batch_result=_batch_with_portfolio_guard_alerts(),
        provider="webhook",
        webhook_url="https://example.invalid/default",
        notify_on="always",
        dry_run=True,
        portfolio_guard_escalation_min=1,
        portfolio_guard_provider="slack_webhook",
        portfolio_guard_webhook_url="https://example.invalid/pg",
    )
    assert out["ok"] is True
    assert out["skipped"] is True
    assert out["reason"] == "dry_run"
    assert out["selected_provider"] == "slack_webhook"
    assert out["route_reason"] == "portfolio_guard_escalation"
    assert out["escalated"] is True


def test_m27_8_notify_keeps_default_provider_when_threshold_not_met():
    out = notifier.notify_batch_result(
        batch_result=_batch_with_portfolio_guard_alerts(),
        provider="webhook",
        webhook_url="https://example.invalid/default",
        notify_on="always",
        dry_run=True,
        portfolio_guard_escalation_min=99,
        portfolio_guard_provider="slack_webhook",
        portfolio_guard_webhook_url="https://example.invalid/pg",
    )
    assert out["ok"] is True
    assert out["selected_provider"] == "webhook"
    assert out["route_reason"] == "default_provider"
    assert out["escalated"] is False
