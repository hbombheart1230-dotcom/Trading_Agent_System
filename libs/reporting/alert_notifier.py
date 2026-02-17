from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict
from urllib import error as urllib_error
from urllib import request as urllib_request


@dataclass(frozen=True)
class NotifyResult:
    ok: bool
    provider: str
    sent: bool
    skipped: bool
    reason: str
    status_code: int
    error: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": bool(self.ok),
            "provider": str(self.provider),
            "sent": bool(self.sent),
            "skipped": bool(self.skipped),
            "reason": str(self.reason),
            "status_code": int(self.status_code),
            "error": str(self.error),
        }


def _as_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    if not s:
        return bool(default)
    return s in ("1", "true", "yes", "y", "on")


def build_batch_notification_payload(batch_result: Dict[str, Any]) -> Dict[str, Any]:
    closeout = batch_result.get("closeout") if isinstance(batch_result.get("closeout"), dict) else {}
    alert_policy = closeout.get("alert_policy") if isinstance(closeout.get("alert_policy"), dict) else {}
    metrics_schema = closeout.get("metrics_schema") if isinstance(closeout.get("metrics_schema"), dict) else {}
    daily_report = closeout.get("daily_report") if isinstance(closeout.get("daily_report"), dict) else {}
    severity_total = alert_policy.get("severity_total") if isinstance(alert_policy.get("severity_total"), dict) else {}

    return {
        "kind": "m25_ops_batch",
        "ok": bool(batch_result.get("ok")),
        "rc": int(batch_result.get("rc") or 0),
        "day": str(batch_result.get("day") or ""),
        "started_ts": str(batch_result.get("started_ts") or ""),
        "finished_ts": str(batch_result.get("finished_ts") or ""),
        "duration_sec": int(batch_result.get("duration_sec") or 0),
        "metrics_schema": {
            "ok": bool(metrics_schema.get("ok")),
            "rc": int(metrics_schema.get("rc") or 0),
            "failure_total": int(metrics_schema.get("failure_total") or 0),
        },
        "alert_policy": {
            "ok": bool(alert_policy.get("ok")),
            "rc": int(alert_policy.get("rc") or 0),
            "alert_total": int(alert_policy.get("alert_total") or 0),
            "severity_total": severity_total,
        },
        "daily_report": {
            "events": int(daily_report.get("events") or 0),
            "path_json": str(daily_report.get("path_json") or ""),
        },
        "failures": batch_result.get("failures") if isinstance(batch_result.get("failures"), list) else [],
    }


def send_webhook_json(
    *,
    webhook_url: str,
    payload: Dict[str, Any],
    timeout_sec: int = 5,
    dry_run: bool = False,
) -> NotifyResult:
    url = str(webhook_url or "").strip()
    if not url:
        return NotifyResult(
            ok=False,
            provider="webhook",
            sent=False,
            skipped=True,
            reason="missing_webhook_url",
            status_code=0,
            error="",
        )
    if bool(dry_run):
        return NotifyResult(
            ok=True,
            provider="webhook",
            sent=False,
            skipped=True,
            reason="dry_run",
            status_code=0,
            error="",
        )

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=max(1, int(timeout_sec))) as resp:
            code = int(getattr(resp, "status", 0) or resp.getcode() or 0)
        ok = 200 <= code < 300
        return NotifyResult(
            ok=ok,
            provider="webhook",
            sent=True,
            skipped=False,
            reason="sent" if ok else "non_2xx",
            status_code=code,
            error="",
        )
    except urllib_error.HTTPError as e:
        code = int(getattr(e, "code", 0) or 0)
        return NotifyResult(
            ok=False,
            provider="webhook",
            sent=True,
            skipped=False,
            reason="http_error",
            status_code=code,
            error=str(e),
        )
    except Exception as e:
        return NotifyResult(
            ok=False,
            provider="webhook",
            sent=True,
            skipped=False,
            reason="send_error",
            status_code=0,
            error=str(e),
        )


def notify_batch_result(
    *,
    batch_result: Dict[str, Any],
    provider: str = "none",
    webhook_url: str = "",
    timeout_sec: int = 5,
    dry_run: bool = False,
    notify_on: str = "failure",
) -> Dict[str, Any]:
    p = str(provider or "none").strip().lower()
    trigger = str(notify_on or "failure").strip().lower()
    if trigger not in ("always", "failure", "success"):
        trigger = "failure"
    ok = bool(batch_result.get("ok"))

    should_send = True
    if trigger == "failure":
        should_send = not ok
    elif trigger == "success":
        should_send = ok

    if p in ("", "none", "off", "disabled"):
        return NotifyResult(
            ok=True,
            provider="none",
            sent=False,
            skipped=True,
            reason="provider_none",
            status_code=0,
            error="",
        ).to_dict()

    if not should_send:
        return NotifyResult(
            ok=True,
            provider=p,
            sent=False,
            skipped=True,
            reason=f"notify_on_{trigger}_skip",
            status_code=0,
            error="",
        ).to_dict()

    if p == "webhook":
        payload = build_batch_notification_payload(batch_result)
        return send_webhook_json(
            webhook_url=webhook_url,
            payload=payload,
            timeout_sec=timeout_sec,
            dry_run=_as_bool(dry_run, default=False),
        ).to_dict()

    return NotifyResult(
        ok=False,
        provider=p,
        sent=False,
        skipped=True,
        reason="unsupported_provider",
        status_code=0,
        error="",
    ).to_dict()
