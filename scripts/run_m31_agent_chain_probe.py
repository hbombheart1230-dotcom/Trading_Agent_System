from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.commander_runtime import run_commander_runtime


@dataclass
class _AllowResult:
    allow: bool
    reason: str = "Allowed"
    details: Dict[str, Any] | None = None


class _StubSupervisor:
    def allow(self, intent: str, context: Dict[str, Any]) -> _AllowResult:
        return _AllowResult(allow=True, reason="Allowed", details={"intent": intent, "stub": True})


@dataclass
class _StubExecutionResult:
    payload: Dict[str, Any]


class _StubExecutor:
    def execute(self, req: Any) -> _StubExecutionResult:
        path = str(getattr(req, "path", "") or "")
        method = str(getattr(req, "method", "") or "")
        body = getattr(req, "body", None)
        return _StubExecutionResult(
            payload={
                "ok": True,
                "stub": True,
                "method": method,
                "path": path,
                "has_body": isinstance(body, dict),
            }
        )


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _build_state(symbol: str, price: float, cash: float) -> Dict[str, Any]:
    sym = str(symbol or "").strip().upper() or "005930"
    px = max(1.0, float(price))
    cs = max(0.0, float(cash))

    return {
        "run_id": uuid.uuid4().hex,
        "symbol": sym,
        "selected_symbol": sym,
        "market_snapshot": {"symbol": sym, "price": px},
        "portfolio_snapshot": {"cash": cs, "open_positions": 0, "positions": []},
        "risk_context": {"daily_pnl_ratio": 0.0, "open_positions": 0, "per_trade_risk_ratio": 0.0},
        "exec_context": {"mode": "mock", "manual_approved": True, "probe": "m31_chain"},
        "policy": {
            "candidate_k": 3,
            "use_global_sentiment": True,
            "use_news_analysis": False,
            "max_risk": 0.70,
            "min_confidence": 0.60,
            "max_scan_retries": 1,
            "use_exit_policy": False,
            "use_position_sizing": False,
        },
        # Keep candidate deterministic for probe readability.
        "candidates": [{"symbol": sym, "why": "probe_seed"}],
        # Force approve-friendly scanner output for first pass.
        "mock_scan_results": {
            sym: {
                "symbol": sym,
                "score": 0.95,
                "risk_score": 0.10,
                "confidence": 0.90,
                "features": {"probe": True},
            }
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M31 integrated agent-chain probe (visibility runner).")
    p.add_argument("--symbol", default="005930")
    p.add_argument("--price", type=float, default=70000.0)
    p.add_argument("--cash", type=float, default=2000000.0)
    p.add_argument("--json", action="store_true")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    state = _build_state(symbol=str(args.symbol), price=float(args.price), cash=float(args.cash))
    state["supervisor"] = _StubSupervisor()
    state["executor"] = _StubExecutor()
    state = run_commander_runtime(state, mode="integrated_chain")

    decision = str(state.get("decision") or "").strip().lower()
    decision_reason = str(state.get("decision_reason") or "")
    execution = state.get("execution") if isinstance(state.get("execution"), dict) else {}
    execution_attempted = bool(execution)
    packet = state.get("decision_packet") if isinstance(state.get("decision_packet"), dict) else {}

    candidates = state.get("candidates") if isinstance(state.get("candidates"), list) else []
    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    monitor = state.get("monitor") if isinstance(state.get("monitor"), dict) else {}
    risk = state.get("risk") if isinstance(state.get("risk"), dict) else {}
    gs = state.get("global_sentiment") if isinstance(state.get("global_sentiment"), dict) else {}
    intents = state.get("intents") if isinstance(state.get("intents"), list) else []

    out: Dict[str, Any] = {
        "ok": decision == "approve" and bool(execution.get("allowed")) if execution_attempted else decision in ("reject", "noop"),
        "run_id": str(state.get("run_id") or ""),
        "commander": {
            "mode": str((state.get("runtime_plan") or {}).get("mode") or "integrated_chain"),
            "chain": list((state.get("runtime_plan") or {}).get("agents") or []),
        },
        "strategist": {
            "candidate_total": len(candidates),
            "candidates": candidates[:3],
            "global_sentiment": _to_float(gs.get("score"), 0.0),
        },
        "scanner": {
            "selected_symbol": selected.get("symbol"),
            "selected_score": _to_float(selected.get("score"), 0.0),
            "risk_score": _to_float(risk.get("risk_score"), 0.0),
            "confidence": _to_float(risk.get("confidence"), 0.0),
        },
        "monitor": {
            "intent_total": len(intents),
            "first_intent": intents[0] if intents else {},
            "has_intent": bool(monitor.get("has_intent")),
        },
        "decision": {
            "decision": decision,
            "reason": decision_reason,
        },
        "packet": packet,
        "execution": {
            "attempted": execution_attempted,
            "allowed": bool(execution.get("allowed")) if execution_attempted else False,
            "reason": str(execution.get("reason") or "") if execution_attempted else "",
            "payload": execution.get("payload") if execution_attempted else {},
        },
        "reporter": {
            "summary": (
                f"decision={decision}, selected={selected.get('symbol')}, "
                f"intent_total={len(intents)}, execution_attempted={execution_attempted}"
            ),
        },
    }

    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(
            f"ok={out['ok']} decision={out['decision']['decision']} "
            f"selected={out['scanner']['selected_symbol']} "
            f"intent_total={out['monitor']['intent_total']} "
            f"execution_attempted={out['execution']['attempted']} "
            f"execution_allowed={out['execution']['allowed']}"
        )
    return 0 if bool(out.get("ok")) else 3


if __name__ == "__main__":
    raise SystemExit(main())
