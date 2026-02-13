from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, Optional

from libs.tools.tool_facade import ToolFacade


def _print(obj: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="M16 approval CLI (preview/approve/reject/list)")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_prev = sub.add_parser("preview", help="Preview intent by id (or last if omitted)")
    p_prev.add_argument("--intent-id", default=None)

    p_app = sub.add_parser("approve", help="Approve intent (marks approved; executes only if EXECUTION_ENABLED=true)")
    p_app.add_argument("--intent-id", default=None)

    p_rej = sub.add_parser("reject", help="Reject intent by id (or last if omitted)")
    p_rej.add_argument("--intent-id", default=None)
    p_rej.add_argument("--reason", default="rejected")

    p_list = sub.add_parser("list", help="List recent intents")
    p_list.add_argument("--limit", type=int, default=10)

    args = p.parse_args(argv)
    api = ToolFacade()

    if args.cmd == "preview":
        _print(api.preview_intent(intent_id=args.intent_id))
        return 0

    if args.cmd == "approve":
        _print(api.approve_intent(intent_id=args.intent_id))
        return 0

    if args.cmd == "reject":
        _print(api.reject_intent(intent_id=args.intent_id, reason=args.reason))
        return 0

    if args.cmd == "list":
        _print(api.list_intents(limit=args.limit))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
