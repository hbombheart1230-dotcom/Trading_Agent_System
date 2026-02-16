from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from graphs.trading_graph import run_trading_graph
from scripts.demo_m22_graph_with_hydration import _build_state, _strategist_passthrough, _to_summary


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="M22 hydration smoke gate")
    p.add_argument("--simulate-timeout", action="store_true")
    p.add_argument("--require-skill-fetch", action="store_true")
    p.add_argument("--require-fallback", action="store_true")
    p.add_argument("--require-no-fallback", action="store_true")
    p.add_argument("--show-json", action="store_true")
    return p


def _fallback_active(summary: Dict[str, Any]) -> bool:
    scanner_skill = summary.get("scanner_skill") if isinstance(summary.get("scanner_skill"), dict) else {}
    monitor = summary.get("monitor") if isinstance(summary.get("monitor"), dict) else {}
    return bool(scanner_skill.get("fallback")) or bool(monitor.get("order_status_fallback"))


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    state = _build_state(fail=bool(args.simulate_timeout))
    out = run_trading_graph(state, strategist=_strategist_passthrough)
    summary = _to_summary(out)

    fetch = summary.get("skill_fetch") if isinstance(summary.get("skill_fetch"), dict) else {}
    fallback = _fallback_active(summary)

    failures: List[str] = []
    if args.require_skill_fetch and not bool(fetch.get("used_runner")):
        failures.append("require-skill-fetch failed: skill_fetch.used_runner is false")

    if args.require_fallback and not fallback:
        failures.append("require-fallback failed: fallback was not detected")

    if args.require_no_fallback and fallback:
        failures.append("require-no-fallback failed: fallback was detected")

    if args.show_json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        selected = summary.get("selected") if isinstance(summary.get("selected"), dict) else {}
        print(
            f"decision={summary.get('decision')} selected={selected.get('symbol')} "
            f"skill_fetch_used={bool(fetch.get('used_runner'))} fallback={fallback}"
        )

    if failures:
        for msg in failures:
            print(msg)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
