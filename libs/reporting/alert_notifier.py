from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Dict, List
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


def _as_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _as_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _dedup_key_from_payload(payload: Dict[str, Any]) -> str:
    basis = {
        "day": payload.get("day"),
        "ok": payload.get("ok"),
        "rc": payload.get("rc"),
        "alert_total": ((payload.get("alert_policy") or {}).get("alert_total") if isinstance(payload.get("alert_policy"), dict) else 0),
        "failures": payload.get("failures") if isinstance(payload.get("failures"), list) else [],
    }
    return json.dumps(basis, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_notify_state(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    events = obj.get("events")
    if not isinstance(events, list):
        return []
    out: List[Dict[str, Any]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        ts = _as_int(ev.get("ts"), 0)
        key = str(ev.get("key") or "")
        if ts <= 0 or not key:
            continue
        out.append({"ts": ts, "key": key})
    return out


def _save_notify_state(path: Path, events: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = {"version": 1, "events": events}
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _prune_events(events: List[Dict[str, Any]], *, now_epoch: int, keep_window_sec: int) -> List[Dict[str, Any]]:
    if keep_window_sec <= 0:
        # Keep bounded history for safety when no window is configured.
        return events[-200:]
    cutoff = now_epoch - keep_window_sec
    return [ev for ev in events if _as_int(ev.get("ts"), 0) >= cutoff]


def _suppression_reason(
    *,
    events: List[Dict[str, Any]],
    now_epoch: int,
    dedup_key: str,
    dedup_window_sec: int,
    rate_limit_window_sec: int,
    max_per_window: int,
) -> str:
    if dedup_window_sec > 0:
        dedup_cutoff = now_epoch - dedup_window_sec
        for ev in events:
            if str(ev.get("key") or "") != dedup_key:
                continue
            if _as_int(ev.get("ts"), 0) >= dedup_cutoff:
                return "dedup_suppressed"

    if rate_limit_window_sec > 0 and max_per_window > 0:
        rl_cutoff = now_epoch - rate_limit_window_sec
        cnt = 0
        for ev in events:
            if _as_int(ev.get("ts"), 0) >= rl_cutoff:
                cnt += 1
        if cnt >= max_per_window:
            return "rate_limited"
    return ""


def _is_retryable_http_status(code: int) -> bool:
    c = int(code or 0)
    return c == 429 or (500 <= c < 600)


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


def build_slack_webhook_payload(batch_payload: Dict[str, Any]) -> Dict[str, Any]:
    alert_policy = batch_payload.get("alert_policy") if isinstance(batch_payload.get("alert_policy"), dict) else {}
    alert_total = int(alert_policy.get("alert_total") or 0)
    failures = batch_payload.get("failures") if isinstance(batch_payload.get("failures"), list) else []
    text = (
        "[M25 batch] "
        f"day={batch_payload.get('day') or ''} "
        f"ok={bool(batch_payload.get('ok'))} "
        f"rc={int(batch_payload.get('rc') or 0)} "
        f"alerts={alert_total} "
        f"failures={len(failures)}"
    )
    return {
        "text": text,
        "metadata": {
            "kind": "m25_ops_batch",
            "day": str(batch_payload.get("day") or ""),
            "rc": int(batch_payload.get("rc") or 0),
            "ok": bool(batch_payload.get("ok")),
        },
    }


def send_webhook_json(
    *,
    provider_name: str = "webhook",
    webhook_url: str,
    payload: Dict[str, Any],
    timeout_sec: int = 5,
    dry_run: bool = False,
    retry_max: int = 0,
    retry_backoff_sec: float = 0.5,
) -> NotifyResult:
    url = str(webhook_url or "").strip()
    if not url:
        return NotifyResult(
            ok=False,
            provider=str(provider_name),
            sent=False,
            skipped=True,
            reason="missing_webhook_url",
            status_code=0,
            error="",
        )
    if bool(dry_run):
        return NotifyResult(
            ok=True,
            provider=str(provider_name),
            sent=False,
            skipped=True,
            reason="dry_run",
            status_code=0,
            error="",
        )

    attempts_max = 1 + max(0, _as_int(retry_max, 0))
    backoff = max(0.0, _as_float(retry_backoff_sec, 0.5))
    attempts = 0
    last_err = ""
    while attempts < attempts_max:
        attempts += 1
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
                provider=str(provider_name),
                sent=True,
                skipped=False,
                reason="sent_after_retry" if (ok and attempts > 1) else ("sent" if ok else "non_2xx"),
                status_code=code,
                error="",
            )
        except urllib_error.HTTPError as e:
            code = int(getattr(e, "code", 0) or 0)
            last_err = str(e)
            if attempts < attempts_max and _is_retryable_http_status(code):
                if backoff > 0:
                    time.sleep(backoff * attempts)
                continue
            return NotifyResult(
                ok=False,
                provider=str(provider_name),
                sent=True,
                skipped=False,
                reason="http_error",
                status_code=code,
                error=last_err,
            )
        except Exception as e:
            last_err = str(e)
            if attempts < attempts_max:
                if backoff > 0:
                    time.sleep(backoff * attempts)
                continue
            return NotifyResult(
                ok=False,
                provider=str(provider_name),
                sent=True,
                skipped=False,
                reason="send_error",
                status_code=0,
                error=last_err,
            )

    return NotifyResult(
        ok=False,
        provider=str(provider_name),
        sent=True,
        skipped=False,
        reason="send_error",
        status_code=0,
        error=last_err,
    )


def notify_batch_result(
    *,
    batch_result: Dict[str, Any],
    provider: str = "none",
    webhook_url: str = "",
    timeout_sec: int = 5,
    dry_run: bool = False,
    notify_on: str = "failure",
    state_path: str = "",
    dedup_window_sec: int = 600,
    rate_limit_window_sec: int = 600,
    max_per_window: int = 3,
    retry_max: int = 0,
    retry_backoff_sec: float = 0.5,
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

    if p in ("webhook", "slack_webhook"):
        batch_payload = build_batch_notification_payload(batch_result)
        now_epoch = int(time.time())
        dedup_key = _dedup_key_from_payload(batch_payload)
        dedup_window = max(0, _as_int(dedup_window_sec, 600))
        rl_window = max(0, _as_int(rate_limit_window_sec, 600))
        rl_max = max(0, _as_int(max_per_window, 3))
        payload = batch_payload if p == "webhook" else build_slack_webhook_payload(batch_payload)

        st_path = Path(str(state_path or "").strip()) if str(state_path or "").strip() else None
        events: List[Dict[str, Any]] = []
        if st_path is not None:
            events = _load_notify_state(st_path)
            reason = _suppression_reason(
                events=events,
                now_epoch=now_epoch,
                dedup_key=dedup_key,
                dedup_window_sec=dedup_window,
                rate_limit_window_sec=rl_window,
                max_per_window=rl_max,
            )
            if reason:
                return NotifyResult(
                    ok=True,
                    provider=p,
                    sent=False,
                    skipped=True,
                    reason=reason,
                    status_code=0,
                    error="",
                ).to_dict()

        result = send_webhook_json(
            provider_name=p,
            webhook_url=webhook_url,
            payload=payload,
            timeout_sec=timeout_sec,
            dry_run=_as_bool(dry_run, default=False),
            retry_max=max(0, _as_int(retry_max, 0)),
            retry_backoff_sec=max(0.0, _as_float(retry_backoff_sec, 0.5)),
        ).to_dict()

        if (
            st_path is not None
            and not _as_bool(dry_run, default=False)
            and bool(result.get("sent"))
            and not bool(result.get("skipped"))
        ):
            events.append({"ts": now_epoch, "key": dedup_key})
            keep_window = max(dedup_window, rl_window, 1)
            events = _prune_events(events, now_epoch=now_epoch, keep_window_sec=keep_window)
            _save_notify_state(st_path, events)
        return result

    return NotifyResult(
        ok=False,
        provider=p,
        sent=False,
        skipped=True,
        reason="unsupported_provider",
        status_code=0,
        error="",
    ).to_dict()
