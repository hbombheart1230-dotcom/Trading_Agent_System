from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Mapping, Tuple


def _to_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return bool(default)
    if isinstance(value, bool):
        return bool(value)
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


@dataclass(frozen=True)
class ScannerBiasContext:
    prefer_shallow_pullback_candidates: bool = False
    penalize_overextended: bool = False
    prefer_reclaim_candidates: bool = False
    prefer_volume_confirmation: bool = False
    bias_strength: str = "low"
    bias_source: str = "scanner_bias.v1"
    validation_issues: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prefer_shallow_pullback_candidates": bool(self.prefer_shallow_pullback_candidates),
            "penalize_overextended": bool(self.penalize_overextended),
            "prefer_reclaim_candidates": bool(self.prefer_reclaim_candidates),
            "prefer_volume_confirmation": bool(self.prefer_volume_confirmation),
            "bias_strength": str(self.bias_strength or "low"),
            "bias_source": str(self.bias_source or "scanner_bias.v1"),
            "validation_issues": [str(x) for x in list(self.validation_issues or []) if str(x or "").strip()],
        }


def build_default_scanner_bias_context() -> ScannerBiasContext:
    return ScannerBiasContext()


def extract_scanner_bias_mapping(raw: Mapping[str, Any] | None) -> Dict[str, Any]:
    data = dict(raw or {})
    for key in ("scanner_bias_context", "scanner_bias"):
        nested = data.get(key)
        if isinstance(nested, dict):
            merged = dict(data)
            merged.update(dict(nested or {}))
            return merged
    return data


def normalize_scanner_bias_context(
    raw: Mapping[str, Any] | ScannerBiasContext | None,
    *,
    bias_source: str = "scanner_bias.v1",
) -> tuple[ScannerBiasContext, Dict[str, Any]]:
    if isinstance(raw, ScannerBiasContext):
        out = raw
        if str(out.bias_source or "").strip() != str(bias_source or "").strip():
            out = ScannerBiasContext(
                prefer_shallow_pullback_candidates=out.prefer_shallow_pullback_candidates,
                penalize_overextended=out.penalize_overextended,
                prefer_reclaim_candidates=out.prefer_reclaim_candidates,
                prefer_volume_confirmation=out.prefer_volume_confirmation,
                bias_strength=out.bias_strength,
                bias_source=str(bias_source or out.bias_source),
                validation_issues=tuple(out.validation_issues),
            )
        return out, {
            "status": "ok",
            "fallback_used": False,
            "issues": list(out.validation_issues or []),
            "bias_source": str(out.bias_source or bias_source),
        }

    mapping = extract_scanner_bias_mapping(raw if isinstance(raw, Mapping) else None)
    default = build_default_scanner_bias_context()
    issues: list[str] = []

    strength = str(mapping.get("bias_strength") or default.bias_strength).strip().lower()
    if strength not in {"low", "medium"}:
        issues.append(f"bias_strength:invalid:{strength or 'missing'}")
        strength = default.bias_strength

    out = ScannerBiasContext(
        prefer_shallow_pullback_candidates=_to_bool(
            mapping.get("prefer_shallow_pullback_candidates"),
            default.prefer_shallow_pullback_candidates,
        ),
        penalize_overextended=_to_bool(
            mapping.get("penalize_overextended"),
            default.penalize_overextended,
        ),
        prefer_reclaim_candidates=_to_bool(
            mapping.get("prefer_reclaim_candidates"),
            default.prefer_reclaim_candidates,
        ),
        prefer_volume_confirmation=_to_bool(
            mapping.get("prefer_volume_confirmation"),
            default.prefer_volume_confirmation,
        ),
        bias_strength=strength,
        bias_source=str(mapping.get("bias_source") or bias_source or default.bias_source),
        validation_issues=tuple(issues),
    )
    return out, {
        "status": "invalid_ignored" if issues else ("ok" if mapping else "missing"),
        "fallback_used": bool(issues),
        "issues": list(issues),
        "bias_source": str(out.bias_source or bias_source),
    }


def summarize_scanner_bias_context(raw: Mapping[str, Any] | ScannerBiasContext | None) -> Dict[str, Any]:
    context, meta = normalize_scanner_bias_context(raw)
    row = context.to_dict()
    active_biases = [
        key
        for key in (
            "prefer_shallow_pullback_candidates",
            "penalize_overextended",
            "prefer_reclaim_candidates",
            "prefer_volume_confirmation",
        )
        if bool(row.get(key))
    ]
    if active_biases:
        summary = f"{', '.join(active_biases)} ({row.get('bias_strength') or 'low'})"
    else:
        summary = "no_bias"
    return {
        "enabled": bool(active_biases),
        "active_biases": active_biases,
        "bias_strength": str(row.get("bias_strength") or "low"),
        "bias_source": str(row.get("bias_source") or meta.get("bias_source") or ""),
        "summary": summary,
        "validation_issues": list(row.get("validation_issues") or meta.get("issues") or []),
    }

