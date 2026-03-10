from __future__ import annotations

import os
from typing import Any, Dict, List

from libs.agent.strategist import Plan
from libs.strategies.candidates.kiwoom_candidate_provider import build_kiwoom_candidate_rows


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _norm_symbol(v: Any) -> str:
    return str(v or "").strip().upper()


def _extract_theme_map(context: Dict[str, Any]) -> Dict[str, set[str]]:
    out: Dict[str, set[str]] = {}
    for key in ("theme_map", "sector_map"):
        raw = context.get(key)
        if not isinstance(raw, dict):
            continue
        for name, symbols in raw.items():
            theme = str(name or "").strip().lower()
            if not theme:
                continue
            bucket = out.setdefault(theme, set())
            if isinstance(symbols, list):
                for sym in symbols:
                    s = _norm_symbol(sym)
                    if s:
                        bucket.add(s)
    return out


class Scanner:
    """Turns a Plan into concrete order intents.

    NOTE: This is a placeholder scaffold. Real scanning logic (signals, ranking, etc.)
    can be added incrementally.
    """

    def scan(self, *, plan: Plan, context: Dict[str, Any]) -> Dict[str, Any] | List[Dict[str, Any]]:
        # If user provides explicit intents, pass-through
        provided = context.get("intents")
        if isinstance(provided, list) and all(isinstance(x, dict) for x in provided):
            return provided

        source = str(context.get("candidate_source") or os.getenv("CANDIDATE_SOURCE", "kiwoom")).strip().lower()
        top_pool = max(1, _to_int(context.get("top_candidate_pool"), _to_int(os.getenv("TOP_CANDIDATE_POOL", "30"), 30)))
        candidate_limit = max(1, _to_int(context.get("top_n_candidates"), _to_int(os.getenv("TOP_N_CANDIDATES", "5"), 5)))
        condition_limit = max(top_pool, _to_int(context.get("candidate_condition_limit"), _to_int(os.getenv("KIWOOM_CANDIDATE_CONDITION_LIMIT", "200"), 200)))

        # Candidate ranking path (additive):
        # Primary source is Kiwoom market data; strategist candidates are fallback hints.
        candidate_rows: List[Dict[str, Any]] = []
        if source in ("kiwoom", "market_data"):
            rows, _meta = build_kiwoom_candidate_rows(
                state=context,
                top_pool=top_pool,
                condition_limit=condition_limit,
                include_change_rate=True,
            )
            themes = [str(x).strip().lower() for x in (getattr(plan, "themes", []) or []) if str(x).strip()]
            theme_idx = _extract_theme_map(context)
            if themes and theme_idx:
                allowed: set[str] = set()
                for t in themes:
                    allowed.update(theme_idx.get(t, set()))
                if allowed:
                    rows = [r for r in rows if _norm_symbol(r.get("symbol")) in allowed]
            candidate_rows = rows[:candidate_limit]

        plan_candidates = list(getattr(plan, "candidates", []) or [])
        if not candidate_rows and plan_candidates:
            candidate_rows = [{"symbol": _norm_symbol(sym), "score": 0.0} for sym in plan_candidates if _norm_symbol(sym)]

        candidate_scores = context.get("candidate_scores") if isinstance(context.get("candidate_scores"), dict) else {}
        ranked: List[Dict[str, Any]] = []
        for row in candidate_rows:
            symbol = _norm_symbol(row.get("symbol"))
            if not symbol:
                continue
            score = 0.0
            try:
                score = float(candidate_scores.get(symbol, row.get("score", 0.0)))
            except Exception:
                score = 0.0
            ranked.append(
                {
                    "symbol": symbol,
                    "score": score,
                    "score_total": score,
                    "score_breakdown": dict(row.get("score_breakdown") or {}),
                    "source": str(row.get("why") or row.get("source") or source),
                }
            )

        ranked.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
        top = ranked[0] if ranked else None

        # Keep legacy contract (`intents` list) while exposing additive scanner output.
        return {
            "intents": [],
            "ranked": ranked,
            "ranked_candidates": ranked,
            "candidate_pool_size": int(len(ranked)),
            "top_stock": (top.get("symbol") if isinstance(top, dict) else None),
            "score": (top.get("score") if isinstance(top, dict) else None),
            "top_score": (top.get("score_total") if isinstance(top, dict) else None),
            "candidate_source": source,
            "themes": list(getattr(plan, "themes", []) or []),
            "candidates": [str(r.get("symbol") or "") for r in candidate_rows],
        }
