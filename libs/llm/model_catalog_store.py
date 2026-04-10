from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.request import urlopen


OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_CATALOG_DIR = Path("data/model_catalog")
DEFAULT_OPENROUTER_MODELS_PATH = DEFAULT_CATALOG_DIR / "openrouter_models.json"
DEFAULT_MODEL_CARDS_PATH = DEFAULT_CATALOG_DIR / "model_cards.json"


STATIC_MODEL_CARD_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "minimax/minimax-m2.5": {
        "tags": ["cheap", "fast", "json_stable"],
        "cost_tier": "free_or_low",
        "latency_tier": "fast",
        "reliability": "high",
        "recommended_roles": ["reporter_intraday", "operator_brief", "lightweight_review"],
        "strengths": [
            "Very low-cost baseline for lightweight structured summaries",
            "Fast enough for intraday reporting surfaces",
            "Stable enough for short JSON-centric reporting tasks",
        ],
        "weaknesses": [
            "Can be weaker on deeper reasoning and nuanced narrative synthesis",
            "Not the best choice for high-context end-of-day analysis",
        ],
        "json_stability_note": "Good baseline for short structured JSON outputs when prompts stay compact.",
        "latency_note": "Typically suitable for fast intraday review paths.",
        "cost_note": "Use when cost pressure matters more than deep reasoning quality.",
        "long_context_note": "Large advertised context exists, but practical use should stay compact for reporting reliability.",
    },
    "deepseek/deepseek-v3.2": {
        "tags": ["cheap", "json_stable", "report_quality"],
        "cost_tier": "low",
        "latency_tier": "medium",
        "reliability": "high",
        "recommended_roles": ["strategist", "balanced_reporting", "general_reasoning"],
        "strengths": [
            "Balanced cost and reasoning quality for operational decision support",
            "Good fit for structured JSON responses with moderate prompt size",
            "Useful default when one model needs to cover both analysis and cost control",
        ],
        "weaknesses": [
            "Latency is not as low as the cheapest fast-path models",
            "May underperform stronger reasoning models on longer narrative synthesis",
        ],
        "json_stability_note": "Good practical default for structured response generation and schema-following.",
        "latency_note": "Usually acceptable for strategist and balanced reporting, but not the fastest option.",
        "cost_note": "Low-cost profile that still preserves solid reasoning utility.",
        "long_context_note": "Context window is sufficient for most current strategist/report payloads without being the main long-context specialist.",
    },
    "moonshotai/kimi-k2.5": {
        "tags": ["reasoning", "long_context", "report_quality", "json_stable"],
        "cost_tier": "medium",
        "latency_tier": "medium",
        "reliability": "high",
        "recommended_roles": ["reporter_daily", "deep_review", "high_context_analysis"],
        "strengths": [
            "Strong fit for longer synthesis and daily review narratives",
            "Good long-context posture for large report payloads",
            "Useful when higher-quality explanation matters more than minimal latency",
        ],
        "weaknesses": [
            "More expensive than the cheaper balanced/fast options",
            "Not the preferred choice for cost-sensitive intraday loops",
        ],
        "json_stability_note": "Generally suitable for structured outputs, especially when prompts are carefully constrained.",
        "latency_note": "Best used on daily or off-path review surfaces rather than the lightest intraday path.",
        "cost_note": "Medium-cost option justified when richer review quality is worth the spend.",
        "long_context_note": "Preferred current baseline when longer evidence packs or richer report context need to be preserved.",
    },
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _provider_from_model_id(model_id: str) -> str:
    text = str(model_id or "").strip()
    if "/" in text:
        return text.split("/", 1)[0]
    return ""


def _supports_json(model_row: Dict[str, Any]) -> bool:
    params = model_row.get("supported_parameters")
    if not isinstance(params, list):
        return False
    supported = {str(item or "").strip().lower() for item in params}
    return bool({"response_format", "structured_outputs"} & supported)


def _derive_cost_tier(model_row: Dict[str, Any]) -> str:
    pricing = model_row.get("pricing") if isinstance(model_row.get("pricing"), dict) else {}
    prompt = _safe_float(pricing.get("prompt"), 0.0)
    completion = _safe_float(pricing.get("completion"), 0.0)
    total = prompt + completion
    if total <= 0.0:
        return "free"
    if total <= 0.000002:
        return "low"
    if total <= 0.00002:
        return "medium"
    return "high"


def _derive_latency_tier(model_row: Dict[str, Any]) -> str:
    model_id = str(model_row.get("id") or "").lower()
    name = str(model_row.get("name") or "").lower()
    joined = f"{model_id} {name}"
    if any(token in joined for token in ("fast", "flash", "mini", ":free")):
        return "fast"
    if any(token in joined for token in ("reasoning", "opus", "r1", "thinking")):
        return "slow"
    return "medium"


def _derive_reliability(model_row: Dict[str, Any]) -> str:
    model_id = str(model_row.get("id") or "").strip()
    if model_id in STATIC_MODEL_CARD_OVERRIDES and STATIC_MODEL_CARD_OVERRIDES[model_id].get("reliability"):
        return str(STATIC_MODEL_CARD_OVERRIDES[model_id]["reliability"])
    if _supports_json(model_row):
        return "medium"
    return "unknown"


def _derive_tags(model_row: Dict[str, Any]) -> List[str]:
    model_id = str(model_row.get("id") or "").strip()
    context_window = int(model_row.get("context_length") or 0)
    pricing = model_row.get("pricing") if isinstance(model_row.get("pricing"), dict) else {}
    prompt_cost = _safe_float(pricing.get("prompt"), 0.0)
    completion_cost = _safe_float(pricing.get("completion"), 0.0)
    tags = set()
    if prompt_cost <= 0.0 and completion_cost <= 0.0:
        tags.add("cheap")
    if any(token in model_id.lower() for token in ("fast", "flash", "mini", ":free")):
        tags.add("fast")
    if _supports_json(model_row):
        tags.add("json_stable")
    if context_window >= 200_000:
        tags.add("long_context")
    if any(token in model_id.lower() for token in ("kimi", "claude", "gpt-5", "gpt-4.1", "gemini-2.5")):
        tags.add("report_quality")
    if any(token in model_id.lower() for token in ("reasoning", "r1", "o1", "o3", "kimi-k2.5", "opus")):
        tags.add("reasoning")
    for tag in STATIC_MODEL_CARD_OVERRIDES.get(model_id, {}).get("tags", []) or []:
        tags.add(str(tag))
    return sorted(str(tag) for tag in tags if str(tag).strip())


def fetch_openrouter_models(
    *,
    url: str = OPENROUTER_MODELS_URL,
    timeout_sec: float = 20.0,
) -> Dict[str, Any]:
    with urlopen(url, timeout=float(timeout_sec)) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = list(payload.get("data") or []) if isinstance(payload, dict) else []
    return {
        "fetched_at": _utc_now_iso(),
        "source": "openrouter",
        "source_url": str(url),
        "fetch_status": "ok",
        "model_count": len(data),
        "data": data,
    }


def load_openrouter_models(path: Path | str = DEFAULT_OPENROUTER_MODELS_PATH) -> Dict[str, Any]:
    return _read_json(Path(path))


def save_openrouter_models(payload: Dict[str, Any], path: Path | str = DEFAULT_OPENROUTER_MODELS_PATH) -> Path:
    target = Path(path)
    _write_json(target, payload)
    return target


def build_model_cards_payload(openrouter_payload: Dict[str, Any]) -> Dict[str, Any]:
    data = list(openrouter_payload.get("data") or []) if isinstance(openrouter_payload, dict) else []
    cards: List[Dict[str, Any]] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        model_id = str(row.get("id") or "").strip()
        if not model_id:
            continue
        pricing = row.get("pricing") if isinstance(row.get("pricing"), dict) else {}
        provider = _provider_from_model_id(model_id)
        card = {
            "model_id": model_id,
            "provider": provider,
            "tags": _derive_tags(row),
            "context_window": int(row.get("context_length") or 0),
            "cost_tier": _derive_cost_tier(row),
            "latency_tier": _derive_latency_tier(row),
            "reliability": _derive_reliability(row),
            "supports_json": _supports_json(row),
            "prompt_cost": _safe_float(pricing.get("prompt"), 0.0),
            "completion_cost": _safe_float(pricing.get("completion"), 0.0),
            "display_name": str(row.get("name") or model_id),
            "recommended_roles": [],
            "strengths": [],
            "weaknesses": [],
            "json_stability_note": "",
            "latency_note": "",
            "cost_note": "",
            "long_context_note": "",
        }
        override = STATIC_MODEL_CARD_OVERRIDES.get(model_id) or {}
        if override.get("cost_tier"):
            card["cost_tier"] = str(override["cost_tier"])
        if override.get("latency_tier"):
            card["latency_tier"] = str(override["latency_tier"])
        if override.get("reliability"):
            card["reliability"] = str(override["reliability"])
        for key in (
            "recommended_roles",
            "strengths",
            "weaknesses",
            "json_stability_note",
            "latency_note",
            "cost_note",
            "long_context_note",
        ):
            if override.get(key) is not None:
                card[key] = override.get(key)
        cards.append(card)
    cards.sort(key=lambda item: str(item.get("model_id") or ""))
    return {
        "generated_at": _utc_now_iso(),
        "source": "openrouter",
        "source_model_count": int(openrouter_payload.get("model_count") or len(cards)),
        "card_count": len(cards),
        "cards": cards,
    }


def load_model_cards(path: Path | str = DEFAULT_MODEL_CARDS_PATH) -> Dict[str, Any]:
    return _read_json(Path(path))


def save_model_cards(payload: Dict[str, Any], path: Path | str = DEFAULT_MODEL_CARDS_PATH) -> Path:
    target = Path(path)
    _write_json(target, payload)
    return target


def get_model_card(
    model_id: str,
    *,
    cards_payload: Optional[Dict[str, Any]] = None,
    path: Path | str = DEFAULT_MODEL_CARDS_PATH,
) -> Dict[str, Any]:
    payload = cards_payload if isinstance(cards_payload, dict) else load_model_cards(path)
    for card in list(payload.get("cards") or []):
        if isinstance(card, dict) and str(card.get("model_id") or "") == str(model_id or ""):
            return dict(card)
    return {}


def list_models_by_tag(
    tag: str,
    *,
    cards_payload: Optional[Dict[str, Any]] = None,
    path: Path | str = DEFAULT_MODEL_CARDS_PATH,
) -> List[Dict[str, Any]]:
    payload = cards_payload if isinstance(cards_payload, dict) else load_model_cards(path)
    target = str(tag or "").strip().lower()
    out: List[Dict[str, Any]] = []
    for card in list(payload.get("cards") or []):
        if not isinstance(card, dict):
            continue
        tags = {str(item or "").strip().lower() for item in list(card.get("tags") or [])}
        if target and target in tags:
            out.append(dict(card))
    return out


def sync_openrouter_model_catalog(
    *,
    url: str = OPENROUTER_MODELS_URL,
    timeout_sec: float = 20.0,
    catalog_dir: Path | str = DEFAULT_CATALOG_DIR,
    allow_cached_fallback: bool = True,
) -> Dict[str, Any]:
    catalog_root = Path(catalog_dir)
    raw_path = catalog_root / DEFAULT_OPENROUTER_MODELS_PATH.name
    cards_path = catalog_root / DEFAULT_MODEL_CARDS_PATH.name
    try:
        openrouter_payload = fetch_openrouter_models(url=url, timeout_sec=timeout_sec)
        fetch_source = "remote"
    except Exception as exc:
        if not allow_cached_fallback or not raw_path.exists():
            raise
        openrouter_payload = load_openrouter_models(raw_path)
        openrouter_payload["fetch_status"] = "cached_fallback"
        openrouter_payload["fetch_error"] = f"{type(exc).__name__}:{exc}"
        fetch_source = "cached_fallback"
    raw_written = save_openrouter_models(openrouter_payload, raw_path)
    cards_payload = build_model_cards_payload(openrouter_payload)
    cards_payload["fetch_source"] = fetch_source
    cards_written = save_model_cards(cards_payload, cards_path)
    return {
        "fetch_source": fetch_source,
        "openrouter_models_path": str(raw_written),
        "model_cards_path": str(cards_written),
        "model_count": int(openrouter_payload.get("model_count") or 0),
        "card_count": int(cards_payload.get("card_count") or 0),
    }
