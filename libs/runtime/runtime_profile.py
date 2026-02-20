from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping


_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_DISABLED_PROVIDERS = {"", "none", "off", "disabled"}
_VALID_PROFILES = {"dev", "staging", "prod"}


def _as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    s = str(value or "").strip().lower()
    if not s:
        return bool(default)
    return s in _TRUE_VALUES


def _norm_profile(value: Any, default: str = "dev") -> str:
    s = str(value or "").strip().lower()
    if s in _VALID_PROFILES:
        return s
    return str(default)


@dataclass(frozen=True)
class RuntimeProfileSpec:
    name: str
    defaults: Dict[str, str]
    required_keys: List[str]
    expected_kiwoom_mode: str


def runtime_profile_spec(profile: str) -> RuntimeProfileSpec:
    p = _norm_profile(profile)
    common_defaults = {
        "APPROVAL_MODE": "manual",
        "EXECUTION_ENABLED": "false",
        "ALLOW_REAL_EXECUTION": "false",
        "EVENT_LOG_PATH": "./data/logs/events.jsonl",
        "REPORT_DIR": "./reports",
        "M25_NOTIFY_PROVIDER": "none",
    }

    if p == "prod":
        defaults = {
            **common_defaults,
            "KIWOOM_MODE": "real",
            "DRY_RUN": "0",
        }
        required = [
            "KIWOOM_APP_KEY",
            "KIWOOM_APP_SECRET",
            "KIWOOM_ACCOUNT_NO",
            "EVENT_LOG_PATH",
            "REPORT_DIR",
        ]
        return RuntimeProfileSpec(
            name="prod",
            defaults=defaults,
            required_keys=required,
            expected_kiwoom_mode="real",
        )

    if p == "staging":
        defaults = {
            **common_defaults,
            "KIWOOM_MODE": "mock",
            "DRY_RUN": "1",
        }
        required = ["EVENT_LOG_PATH", "REPORT_DIR"]
        return RuntimeProfileSpec(
            name="staging",
            defaults=defaults,
            required_keys=required,
            expected_kiwoom_mode="mock",
        )

    defaults = {
        **common_defaults,
        "KIWOOM_MODE": "mock",
        "DRY_RUN": "1",
    }
    required = ["EVENT_LOG_PATH", "REPORT_DIR"]
    return RuntimeProfileSpec(
        name="dev",
        defaults=defaults,
        required_keys=required,
        expected_kiwoom_mode="mock",
    )


def profile_effective_env(
    profile: str,
    environ: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    env = environ or {}
    spec = runtime_profile_spec(profile)
    keys: List[str] = []
    seen = set()

    for k in list(spec.defaults.keys()) + list(spec.required_keys):
        if k in seen:
            continue
        keys.append(k)
        seen.add(k)

    out: Dict[str, str] = {}
    for k in keys:
        raw = str(env.get(k, "")).strip()
        if raw:
            out[k] = raw
        else:
            out[k] = str(spec.defaults.get(k, ""))
    return out


def validate_runtime_profile(
    profile: str,
    environ: Mapping[str, str] | None = None,
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    env = environ or {}
    spec = runtime_profile_spec(profile)
    effective = profile_effective_env(spec.name, environ=env)

    missing_required: List[str] = []
    violations: List[str] = []
    warnings: List[str] = []

    for key in spec.required_keys:
        if str(env.get(key, "")).strip():
            continue
        default_val = str(spec.defaults.get(key, "")).strip()
        if default_val:
            continue
        missing_required.append(key)

    mode = str(effective.get("KIWOOM_MODE", "")).strip().lower()
    if mode != spec.expected_kiwoom_mode:
        violations.append(
            f"KIWOOM_MODE mismatch: expected={spec.expected_kiwoom_mode} actual={mode or '(empty)'}"
        )

    execution_enabled = _as_bool(effective.get("EXECUTION_ENABLED"), default=False)
    allow_real = _as_bool(effective.get("ALLOW_REAL_EXECUTION"), default=False)

    if execution_enabled and (mode != "real"):
        violations.append("EXECUTION_ENABLED=true requires KIWOOM_MODE=real")
    if execution_enabled and not allow_real:
        violations.append("EXECUTION_ENABLED=true requires ALLOW_REAL_EXECUTION=true")
    if (spec.name in ("dev", "staging")) and execution_enabled:
        warnings.append(f"{spec.name} profile normally keeps EXECUTION_ENABLED=false")

    provider = str(effective.get("M25_NOTIFY_PROVIDER", "")).strip().lower()
    if (spec.name == "prod") and (provider in _DISABLED_PROVIDERS):
        warnings.append("prod profile should configure M25_NOTIFY_PROVIDER")

    if strict and warnings:
        violations.extend([f"strict:{msg}" for msg in warnings])

    return {
        "ok": (len(missing_required) == 0) and (len(violations) == 0),
        "profile": spec.name,
        "strict": bool(strict),
        "required_missing": missing_required,
        "violations": violations,
        "warnings": warnings,
        "effective": effective,
        "defaults": dict(spec.defaults),
    }


def valid_runtime_profiles() -> Iterable[str]:
    return ("dev", "staging", "prod")
