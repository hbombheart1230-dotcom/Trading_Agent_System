from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.commander_runtime import run_commander_runtime, RuntimeMode


def _stub_graph_runner(state: Dict[str, Any]) -> Dict[str, Any]:
    state["path"] = "graph_spine"
    state["decision"] = "noop"
    return state


def _stub_decide(state: Dict[str, Any]) -> Dict[str, Any]:
    state["decision_packet"] = {
        "intent": {"action": "NOOP", "symbol": "", "qty": 0, "price": 0, "order_type": "market"},
        "risk": {},
        "exec_context": {},
    }
    return state


def _stub_execute(state: Dict[str, Any]) -> Dict[str, Any]:
    state["path"] = "decision_packet"
    state["execution"] = {"allowed": True, "reason": "smoke"}
    return state


def _stub_integrated_runner(state: Dict[str, Any]) -> Dict[str, Any]:
    state["path"] = "integrated_chain"
    state["decision"] = "approve"
    state["execution"] = {"allowed": True, "reason": "smoke_integrated"}
    return state


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run canonical commander runtime once.")
    p.add_argument("--mode", choices=["graph_spine", "decision_packet", "integrated_chain"], default=None)
    p.add_argument("--runtime-control", choices=["retry", "pause", "cancel", "resume"], default=None)
    p.add_argument("--run-id", default="m21-runtime-once")
    p.add_argument("--live", action="store_true", help="Use real node path instead of offline smoke stubs.")
    p.add_argument("--json", action="store_true", help="Emit compact JSON summary.")
    return p


def _to_summary(out: Dict[str, Any], *, live: bool) -> Dict[str, Any]:
    execution = out.get("execution") if isinstance(out.get("execution"), dict) else {}
    runtime_plan = out.get("runtime_plan") if isinstance(out.get("runtime_plan"), dict) else {}
    return {
        "live": bool(live),
        "runtime_status": out.get("runtime_status", "running"),
        "runtime_transition": out.get("runtime_transition"),
        "runtime_mode": runtime_plan.get("mode"),
        "runtime_agents": runtime_plan.get("agents", []),
        "path": out.get("path"),
        "decision": out.get("decision"),
        "execution_allowed": execution.get("allowed"),
    }


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    state: Dict[str, Any] = {"run_id": args.run_id}
    if args.runtime_control:
        state["runtime_control"] = args.runtime_control

    typed_mode = cast(Optional[RuntimeMode], args.mode)

    if args.live:
        out = run_commander_runtime(state, mode=typed_mode)
    else:
        out = run_commander_runtime(
            state,
            mode=typed_mode,
            graph_runner=_stub_graph_runner,
            integrated_runner=_stub_integrated_runner,
            decide=_stub_decide,
            execute=_stub_execute,
        )

    summary = _to_summary(out, live=args.live)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        print(
            f"mode={summary.get('runtime_mode')} status={summary.get('runtime_status')} "
            f"transition={summary.get('runtime_transition')} path={summary.get('path')} "
            f"execution_allowed={summary.get('execution_allowed')}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
