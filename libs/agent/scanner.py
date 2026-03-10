from __future__ import annotations

from typing import Any, Dict, List

from libs.agent.strategist import Plan


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

        # Candidate-only ranking path (additive):
        # Scanner evaluates Strategist-provided candidates instead of blind universe scan.
        candidate_scores = context.get("candidate_scores") if isinstance(context.get("candidate_scores"), dict) else {}
        ranked: List[Dict[str, Any]] = []
        for sym in list(getattr(plan, "candidates", []) or []):
            symbol = str(sym or "").strip().upper()
            if not symbol:
                continue
            score = 0.0
            try:
                score = float(candidate_scores.get(symbol, 0.0))
            except Exception:
                score = 0.0
            ranked.append({"symbol": symbol, "score": score})

        ranked.sort(key=lambda r: float(r.get("score") or 0.0), reverse=True)
        top = ranked[0] if ranked else None

        # Keep legacy contract (`intents` list) while exposing additive scanner output.
        return {
            "intents": [],
            "ranked": ranked,
            "top_stock": (top.get("symbol") if isinstance(top, dict) else None),
            "score": (top.get("score") if isinstance(top, dict) else None),
            "themes": list(getattr(plan, "themes", []) or []),
            "candidates": list(getattr(plan, "candidates", []) or []),
        }
