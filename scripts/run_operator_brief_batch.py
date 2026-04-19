from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.core.settings import load_env_file


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _trade_brief_llm_path(trade_dir: Path) -> Path:
    return trade_dir / "reports" / "brief_llm_response.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate operator briefs under reports/trades for one day.")
    parser.add_argument("--env-path", default=".env")
    parser.add_argument("--day", required=True)
    parser.add_argument("--trade-id", action="append", default=[], help="Optional trade_id filter. Repeat the flag to process multiple trades.")
    parser.add_argument("--force", action="store_true", help="Force brief regeneration even if saved artifacts already exist.")
    parser.add_argument("--json", action="store_true")
    return parser


def _normalize_trade_id_filters(values: Any) -> List[str]:
    raw_values: List[str] = []
    if isinstance(values, list):
        raw_values = [str(value or "") for value in values]
    elif values not in (None, ""):
        raw_values = [str(values or "")]
    out: List[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        for part in str(raw or "").split(","):
            trade_id = str(part or "").strip()
            if not trade_id or trade_id in seen:
                continue
            out.append(trade_id)
            seen.add(trade_id)
    return out


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    load_env_file(str(args.env_path).strip() or ".env")
    if bool(args.force):
        os.environ["OPERATOR_UI_RUN_BRIEF_FORCE_REGENERATE"] = "1"

    from apps.operator_ui import data_access as dac

    cfg = dac.OperatorUIConfig.from_env()
    day = str(args.day or "").strip()
    trade_day_root = cfg.reports_root / "trades" / day
    if not trade_day_root.exists():
        out = {"ok": False, "day": day, "error": "trade_day_root_not_found", "path": str(trade_day_root)}
        print(json.dumps(out, ensure_ascii=False) if bool(args.json) else f"ok=false error=trade_day_root_not_found path={trade_day_root}")
        return 3

    rows: List[Dict[str, Any]] = []
    trade_dirs = sorted(path for path in trade_day_root.iterdir() if path.is_dir())
    trade_id_filters = _normalize_trade_id_filters(args.trade_id)
    if trade_id_filters:
        allowed = set(trade_id_filters)
        trade_dirs = [path for path in trade_dirs if path.name in allowed]
    for trade_dir in trade_dirs:
        story_id = trade_dir.name
        brief = dac.load_operator_brief_detail(cfg, story_id)
        llm_path = _trade_brief_llm_path(trade_dir)
        llm_artifact = _read_json(llm_path)
        rows.append(
            {
                "story_id": story_id,
                "found": bool(brief.get("found")),
                "status": str(brief.get("status") or ""),
                "model": str(brief.get("model") or ""),
                "brief_json_path": str(((brief.get("paths") or {}).get("operator_brief_json") or "")),
                "brief_md_path": str(((brief.get("paths") or {}).get("operator_brief_md") or "")),
                "brief_input_path": str(trade_dir / "brief_input.json"),
                "brief_compact_input_path": str(trade_dir / "brief_compact_input.json"),
                "brief_llm_response_path": str(llm_path) if llm_path.exists() else "",
                "brief_llm_status": str(llm_artifact.get("status") or ""),
                "brief_llm_model": str(llm_artifact.get("model") or ((llm_artifact.get("model_info") or {}).get("model")) or ""),
                "brief_llm_retry_count": int(llm_artifact.get("retry_count") or 0),
                "brief_llm_error": str(llm_artifact.get("error") or ((llm_artifact.get("meta") or {}).get("reason") or "")),
            }
        )

    out = {
        "ok": True,
        "day": day,
        "trade_count": len(rows),
        "rows": rows,
    }
    if bool(args.json):
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(f"ok=true day={day} trade_count={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
