from __future__ import annotations

from typing import Any, Dict, List, Optional
from pathlib import Path


class Reporter:
    """Reporter agent (passive).

    - Runtime role: summarize current run payloads (`build`)
    - Post-run role: generate log-derived analysis artifacts (`analyze_event_logs`)
    - Boundary: must not affect live trading decisions or execution flow.
    - Note: AI-centered reporter enhancement is planned later; current role is
      deterministic log summarization and operator-facing analysis.
    """

    def build(
        self,
        *,
        run_id: str,
        context: Dict[str, Any],
        plan: Any,
        intents: List[Dict[str, Any]],
        decisions: List[Dict[str, Any]],
        executions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        latest_intent = intents[-1] if intents else {}
        latest_decision = decisions[-1] if decisions else {}
        latest_execution = executions[-1] if executions else {}
        return {
            "run_id": run_id,
            "plan": getattr(plan, "__dict__", str(plan)),
            "intents_count": len(intents),
            "decisions_count": len(decisions),
            "executions_count": len(executions),
            "latest_intent": latest_intent,
            "latest_decision": latest_decision,
            "latest_execution": latest_execution,
            "context_keys": sorted(list(context.keys())),
        }

    def analyze_event_logs(
        self,
        *,
        event_log_path: str | Path = "data/logs/events.jsonl",
        report_dir: str | Path = "reports/reporter_analysis",
        day: Optional[str] = None,
        intents_path: str | Path = "data/logs/intents.jsonl",
        reports_root: str | Path = "reports",
        rapid_cycle_threshold_sec: int = 120,
        ai_review_enabled: Optional[bool] = None,
        ai_review_model: Optional[str] = None,
        ai_review_temperature: Optional[float] = None,
        ai_review_max_tokens: int = 900,
    ) -> Dict[str, Any]:
        """Generate passive post-run reporter analysis from append-only logs."""
        from libs.reporting.reporter_analysis import generate_reporter_analysis_report

        e = Path(str(event_log_path))
        r = Path(str(report_dir))
        i = Path(str(intents_path))
        root = Path(str(reports_root))
        _md, _js, out = generate_reporter_analysis_report(
            e,
            r,
            day=day,
            intents_path=i if i.exists() else None,
            reports_root=root,
            rapid_cycle_threshold_sec=max(1, int(rapid_cycle_threshold_sec)),
            ai_review_enabled=ai_review_enabled,
            ai_review_model=ai_review_model,
            ai_review_temperature=ai_review_temperature,
            ai_review_max_tokens=max(256, int(ai_review_max_tokens)),
        )
        return out
