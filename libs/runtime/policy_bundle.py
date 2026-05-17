from __future__ import annotations

from typing import Any, Dict, Tuple


STRATEGY_POLICY_SECTIONS: Tuple[str, ...] = (
    "market_policy",
    "scanner_policy",
    "entry_policy",
    "monitor_policy",
    "decision_policy",
    "operator_explain",
)


def normalize_strategy_policy_bundle(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    out = dict(raw)
    out["schema_version"] = str(raw.get("schema_version") or "strategy_policy.v1")
    for section in STRATEGY_POLICY_SECTIONS:
        out[section] = dict(raw.get(section) or {}) if isinstance(raw.get(section), dict) else {}
    return out


def strategy_policy_bundle_summary(policy: Any) -> Dict[str, Any]:
    bundle = normalize_strategy_policy_bundle(policy)
    return {
        "schema_version": str(bundle.get("schema_version") or "strategy_policy.v1"),
        "sections": {
            section: {
                "available": bool(bundle.get(section)),
                "keys": sorted(str(k) for k in list((bundle.get(section) or {}).keys())),
            }
            for section in STRATEGY_POLICY_SECTIONS
        },
    }
