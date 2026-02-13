from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


def _stable_unit_hash(text: str) -> float:
    """Return a deterministic pseudo-random float in [0, 1).

    We avoid Python's built-in hash() because it is salted per-process.
    """
    # A tiny, deterministic rolling hash
    h = 0
    for ch in text:
        h = (h * 131 + ord(ch)) % 10_000
    return (h % 10_000) / 10_000.0


def scanner_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Scanner (Data + feature extraction).

    M17-3 contract:
      - Reads state['candidates'] produced by strategist_node
      - Computes per-candidate features/risk/confidence
      - Selects exactly 1 candidate into state['selected'] (or None)

    Writes:
      - state['scan_results'] : list[dict]
      - state['selected'] : dict | None
      - state['risk'] : dict (risk_score/confidence for selected)

    Test hooks:
      - state['mock_scan_results'] : {symbol: {score, risk_score, confidence, features?}}
        If present, Scanner will use these values instead of generating.
    """
    candidates = state.get("candidates") or []
    if not isinstance(candidates, list):
        candidates = []

    mock: Optional[Mapping[str, Any]] = state.get("mock_scan_results")  # for tests

    scan_results: List[Dict[str, Any]] = []

    for item in candidates:
        if isinstance(item, dict):
            symbol = str(item.get("symbol") or "")
        else:
            symbol = str(item)

        if not symbol:
            continue

        if isinstance(mock, Mapping) and symbol in mock:
            row = dict(mock[symbol])
            row.setdefault("symbol", symbol)
        else:
            base = _stable_unit_hash(symbol)
            # Simple deterministic defaults (placeholder)
            score = 1.0 - base  # higher is better
            risk_score = base  # higher is riskier
            confidence = max(0.0, min(1.0, 0.9 - base * 0.4))
            row = {
                "symbol": symbol,
                "score": float(score),
                "risk_score": float(risk_score),
                "confidence": float(confidence),
                "features": {
                    "unit_hash": float(base),
                },
            }

        scan_results.append(row)

    # Sort by score desc, then confidence desc, then risk asc
    scan_results_sorted = sorted(
        scan_results,
        key=lambda r: (
            float(r.get("score") or 0.0),
            float(r.get("confidence") or 0.0),
            -float(r.get("risk_score") or 0.0),
        ),
        reverse=True,
    )

    selected = scan_results_sorted[0] if scan_results_sorted else None
    state["scan_results"] = scan_results_sorted
    state["selected"] = selected

    # Provide a normalized risk snapshot for Decision Node.
    if isinstance(selected, dict):
        state["risk"] = {
            "risk_score": float(selected.get("risk_score") or 0.0),
            "confidence": float(selected.get("confidence") or 0.0),
        }
    else:
        state["risk"] = {"risk_score": 0.0, "confidence": 0.0}

    return state
