from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from libs.agent.reporter_inputs import ReporterInput
from libs.agent.reporter_outputs import ReporterOutput
from libs.reporting.reporter_feedback import build_strategist_feedback_packet


class Reporter:
    """Reporter agent.

    Runtime role:
    - summarize current run payloads (`build`)

    Reporting role:
    - orchestrate deterministic post-run report generation while reusing the
      existing libs/reporting and script-level generators

    Boundary:
    - must not affect live trading decisions or execution flow
    - runtime trading semantics remain unchanged
    """

    def _path(self, value: str | Path) -> Path:
        return value if isinstance(value, Path) else Path(str(value))

    def _read_json(self, path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _normalize_day(self, day: Optional[str]) -> Optional[str]:
        if day is None:
            return None
        normalized = str(day).strip()
        return normalized or None

    def _hook_result(
        self,
        *,
        hook_name: str,
        enabled: bool,
        status: str,
        executed: bool = False,
        reason: str = "",
        day: Optional[str] = None,
        report_type: str = "",
        output_paths: Optional[Dict[str, str]] = None,
        warnings: Optional[List[str]] = None,
        data_freshness: Optional[Dict[str, Any]] = None,
        strategist_feedback_packet: Optional[Dict[str, Any]] = None,
        generated_reports: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "hook_name": str(hook_name or ""),
            "enabled": bool(enabled),
            "status": str(status or ""),
            "executed": bool(executed),
            "reason": str(reason or ""),
            "day": self._normalize_day(day),
            "report_only": True,
            "execution_authority": False,
            "route_override_authority": False,
            "threshold_override_authority": False,
            "report_type": str(report_type or ""),
            "output_paths": dict(output_paths or {}),
            "warnings": list(warnings or []),
            "data_freshness": dict(data_freshness or {}),
            "generated_reports": list(generated_reports or []),
            "strategist_feedback_reserved": hook_name == "strategist_feedback",
            "strategist_feedback_packet": dict(strategist_feedback_packet or {}) if isinstance(strategist_feedback_packet, dict) else None,
        }

    def _guess_reports_root(self, path: Optional[Path]) -> Path:
        if path is None:
            return self._path(".")
        for candidate in (path.parent if path.suffix else path, *(path.parents)):
            if candidate.name == "reports":
                return candidate
        return path.parent if path.suffix else path

    def _result(
        self,
        *,
        mode: str,
        payload: Dict[str, Any],
        reporter_input: Optional[ReporterInput] = None,
        report_md_path: Optional[Path] = None,
        report_json_path: Optional[Path] = None,
    ) -> ReporterOutput:
        out = dict(payload or {})
        out.setdefault("mode", mode)
        if report_md_path is not None:
            out.setdefault("report_md_path", str(report_md_path))
        if report_json_path is not None:
            out.setdefault("report_json_path", str(report_json_path))
        data_freshness = out.get("data_freshness") if isinstance(out.get("data_freshness"), dict) else {}
        route_provenance = out.get("route_provenance") if isinstance(out.get("route_provenance"), dict) else {}
        warnings: List[str] = []
        if not data_freshness:
            warnings.append("missing_data_freshness")
        if not route_provenance:
            warnings.append("missing_route_provenance")
        if report_json_path is None and not str(out.get("report_json_path") or "").strip():
            warnings.append("missing_report_json_path")
        if report_md_path is None and not str(out.get("report_md_path") or "").strip():
            warnings.append("missing_report_md_path")
        input_contract = reporter_input or self._build_reporter_input(
            mode=mode,
            reports_root=self._guess_reports_root(report_json_path or report_md_path),
            payload=out,
        )
        strategist_feedback_packet = (
            dict(out.get("strategist_feedback_packet") or {})
            if isinstance(out.get("strategist_feedback_packet"), dict)
            else build_strategist_feedback_packet(
                mode=mode,
                payload=out,
                reports_root=input_contract.reports_root,
                day=input_contract.day,
            )
        )
        return ReporterOutput(
            report_type=mode,
            output_paths={
                "md": str(report_md_path) if report_md_path is not None else str(out.get("report_md_path") or ""),
                "json": str(report_json_path) if report_json_path is not None else str(out.get("report_json_path") or ""),
            },
            generated_at=str(out.get("generated_at") or data_freshness.get("generated_at") or ""),
            data_freshness=dict(data_freshness),
            route_provenance=dict(route_provenance),
            narrative_axis_policy=dict(out.get("narrative_axis_policy") or {}) if isinstance(out.get("narrative_axis_policy"), dict) else None,
            summary_metadata={
                "day": str(out.get("day") or ""),
                "source_run_count": int(out.get("source_run_count") or data_freshness.get("source_run_count") or 0),
                "latest_run_id": str(out.get("latest_run_id") or data_freshness.get("latest_run_id") or ""),
                "latest_run_ts": str(out.get("latest_run_ts") or data_freshness.get("latest_run_ts") or ""),
                "available_surfaces": list(input_contract.available_surfaces),
                "generation_mode": input_contract.generation_mode,
                "reporter_input": input_contract.to_dict(),
            },
            strategist_feedback_packet=strategist_feedback_packet,
            operator_packet=dict(out.get("operator_packet") or {}) if isinstance(out.get("operator_packet"), dict) else None,
            success=len(warnings) == 0,
            warnings=warnings,
            payload=out,
        )

    def _build_reporter_input(
        self,
        *,
        mode: str,
        reports_root: Path,
        payload: Dict[str, Any],
        flags: Optional[Dict[str, Any]] = None,
    ) -> ReporterInput:
        root = self._path(reports_root)
        route_summary = payload.get("route_summary") if isinstance(payload.get("route_summary"), dict) else {}
        data_freshness = payload.get("data_freshness") if isinstance(payload.get("data_freshness"), dict) else {}
        available_surfaces: List[str] = []
        if str(payload.get("report_md_path") or "").strip():
            available_surfaces.append("markdown")
        if str(payload.get("report_json_path") or "").strip():
            available_surfaces.append("json")
        for name in ("route_summary", "data_freshness", "narrative_axis_policy"):
            if isinstance(payload.get(name), dict):
                available_surfaces.append(name)
        return ReporterInput(
            day=str(payload.get("day") or ""),
            reports_root=root,
            canonical_report_root=root,
            run_ids=[],
            source_run_count=int(payload.get("source_run_count") or data_freshness.get("source_run_count") or 0),
            latest_run_id=str(payload.get("latest_run_id") or data_freshness.get("latest_run_id") or ""),
            latest_run_ts=str(payload.get("latest_run_ts") or data_freshness.get("latest_run_ts") or ""),
            route_summary=dict(route_summary),
            data_freshness=dict(data_freshness),
            available_surfaces=available_surfaces,
            narrative_axis_policy=dict(payload.get("narrative_axis_policy") or {}) if isinstance(payload.get("narrative_axis_policy"), dict) else None,
            generation_mode="deterministic",
            flags=dict(flags or {"mode": mode}),
        )

    def run(self, *, mode: str, **kwargs: Any) -> ReporterOutput | Dict[str, Any]:
        dispatch: Dict[str, Callable[..., ReporterOutput | Dict[str, Any]]] = {
            "daily_report": self.generate_daily_report,
            "operator_summary": self.generate_operator_summary,
            "trade_explain": self.generate_trade_explain,
            "metrics_report": self.generate_metrics_report,
            "run_cards": self.generate_run_cards,
            "decision_story": self.generate_decision_story,
            "reporter_analysis": self.analyze_event_logs,
        }
        handler = dispatch.get(str(mode).strip())
        if handler is None:
            raise ValueError(f"unsupported reporter mode: {mode}")
        result = handler(**kwargs)
        if isinstance(result, ReporterOutput):
            return result
        if str(mode).strip() == "reporter_analysis" and isinstance(result, dict):
            report_md = str(result.get("report_md_path") or "")
            report_json = str(result.get("report_json_path") or "")
            return self._result(
                mode="reporter_analysis",
                payload=result,
                report_md_path=Path(report_md) if report_md else None,
                report_json_path=Path(report_json) if report_json else None,
            )
        return {"mode": str(mode).strip(), "payload": result}

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
        report_dir: str | Path = "reports/dev/analysis/reporter_analysis",
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

    def generate_daily_report(
        self,
        *,
        event_log_path: str | Path = "data/logs/events.jsonl",
        reports_root: str | Path = "reports",
        day: Optional[str] = None,
    ) -> ReporterOutput:
        from libs.reporting.daily_report_generator import generate_daily_report as generate

        events_path = self._path(event_log_path)
        root = self._path(reports_root)
        normalized_day = self._normalize_day(day)
        md_path, js_path = generate(events_path, root, day=normalized_day)
        payload = self._read_json(js_path)
        return self._result(
            mode="daily_report",
            payload=payload,
            reporter_input=self._build_reporter_input(
                mode="daily_report",
                reports_root=root,
                payload=payload,
                flags={"day": normalized_day},
            ),
            report_md_path=md_path,
            report_json_path=js_path,
        )

    def generate_operator_summary(
        self,
        *,
        event_log_path: str | Path = "data/logs/events.jsonl",
        report_dir: str | Path = "reports",
        day: Optional[str] = None,
        metrics_report_dir: str | Path | None = None,
        m30_post_golive_dir: str | Path | None = None,
        m30_golive_dir: str | Path | None = None,
        m31_slo_incident_dir: str | Path | None = None,
    ) -> ReporterOutput:
        from libs.reporting.operator_visibility import generate_operator_daily_summary

        events_path = self._path(event_log_path)
        root = self._path(report_dir)
        reports_root = root
        md_path, js_path = generate_operator_daily_summary(
            events_path,
            root,
            day=self._normalize_day(day),
            metrics_report_dir=self._path(metrics_report_dir) if metrics_report_dir is not None else reports_root / "metrics",
            m30_post_golive_dir=self._path(m30_post_golive_dir) if m30_post_golive_dir is not None else reports_root / "milestones" / "m30_post_golive",
            m30_golive_dir=self._path(m30_golive_dir) if m30_golive_dir is not None else reports_root / "milestones" / "m30_golive",
            m31_slo_incident_dir=self._path(m31_slo_incident_dir) if m31_slo_incident_dir is not None else reports_root / "milestones" / "m31_slo_incident",
        )
        payload = self._read_json(js_path)
        return self._result(
            mode="operator_summary",
            payload=payload,
            reporter_input=self._build_reporter_input(
                mode="operator_summary",
                reports_root=reports_root,
                payload=payload,
                flags={"day": self._normalize_day(day)},
            ),
            report_md_path=md_path,
            report_json_path=js_path,
        )

    def generate_trade_explain(
        self,
        *,
        event_log_path: str | Path = "data/logs/events.jsonl",
        report_dir: str | Path | None = None,
        reports_root: str | Path = "reports",
        day: Optional[str] = None,
        max_executions: int = 120,
        max_sell_pairs: int = 120,
    ) -> ReporterOutput:
        from libs.reporting.trade_explain import (
            generate_trade_explain_report,
            official_trade_explain_report_dir,
        )

        events_path = self._path(event_log_path)
        root = self._path(reports_root)
        target_dir = self._path(report_dir) if report_dir is not None else official_trade_explain_report_dir(root)
        md_path, js_path, out = generate_trade_explain_report(
            events_path,
            target_dir,
            day=self._normalize_day(day),
            max_executions=max(1, int(max_executions)),
            max_sell_pairs=max(1, int(max_sell_pairs)),
        )
        return self._result(
            mode="trade_explain",
            payload=out,
            reporter_input=self._build_reporter_input(
                mode="trade_explain",
                reports_root=root,
                payload=out,
                flags={
                    "day": self._normalize_day(day),
                    "max_executions": max(1, int(max_executions)),
                    "max_sell_pairs": max(1, int(max_sell_pairs)),
                },
            ),
            report_md_path=md_path,
            report_json_path=js_path,
        )

    def generate_metrics_report(
        self,
        *,
        event_log_path: str | Path = "data/logs/events.jsonl",
        report_dir: str | Path = "reports/metrics",
        day: Optional[str] = None,
    ) -> ReporterOutput:
        from libs.reporting.metrics_report_generator import generate_metrics_report as generate

        events_path = self._path(event_log_path)
        out_dir = self._path(report_dir)
        md_path, js_path = generate(events_path, out_dir, day=self._normalize_day(day))
        payload = self._read_json(js_path)
        return self._result(
            mode="metrics_report",
            payload=payload,
            reporter_input=self._build_reporter_input(
                mode="metrics_report",
                reports_root=out_dir.parent if out_dir.name == "metrics" else out_dir,
                payload=payload,
                flags={"day": self._normalize_day(day)},
            ),
            report_md_path=md_path,
            report_json_path=js_path,
        )

    def generate_run_cards(
        self,
        *,
        event_log_path: str | Path = "data/logs/events.jsonl",
        report_dir: str | Path = "reports/dev/manual/run_cards",
        day: Optional[str] = None,
        max_runs: int = 120,
        trade_only: bool = True,
    ) -> ReporterOutput:
        from libs.reporting.operator_visibility import generate_run_card_report

        events_path = self._path(event_log_path)
        out_dir = self._path(report_dir)
        md_path, out = generate_run_card_report(
            events_path,
            out_dir,
            day=self._normalize_day(day),
            max_runs=max(0, int(max_runs)),
            trade_only=bool(trade_only),
        )
        return self._result(
            mode="run_cards",
            payload=dict(out or {}),
            reporter_input=self._build_reporter_input(
                mode="run_cards",
                reports_root=out_dir,
                payload=dict(out or {}),
                flags={"day": self._normalize_day(day), "trade_only": bool(trade_only)},
            ),
            report_md_path=md_path,
        )

    def generate_decision_story(
        self,
        *,
        event_log_path: str | Path = "data/logs/events.jsonl",
        report_dir: str | Path = "reports/dev/manual/decision_story",
        day: Optional[str] = None,
        max_runs: int = 120,
        trade_only: bool = True,
    ) -> ReporterOutput:
        from libs.reporting.operator_visibility import generate_decision_story_report

        events_path = self._path(event_log_path)
        out_dir = self._path(report_dir)
        md_path, out = generate_decision_story_report(
            events_path,
            out_dir,
            day=self._normalize_day(day),
            max_runs=max(0, int(max_runs)),
            trade_only=bool(trade_only),
        )
        return self._result(
            mode="decision_story",
            payload=dict(out or {}),
            reporter_input=self._build_reporter_input(
                mode="decision_story",
                reports_root=out_dir,
                payload=dict(out or {}),
                flags={"day": self._normalize_day(day), "trade_only": bool(trade_only)},
            ),
            report_md_path=md_path,
        )

    def maybe_generate_intraday_summary(
        self,
        *,
        enabled: bool = False,
        emit_reports: bool = False,
        event_log_path: str | Path = "data/logs/events.jsonl",
        reports_root: str | Path = "reports",
        day: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Optional commander hook for intraday analysis.

        This hook is analysis-only. It must never influence route selection,
        thresholds, approvals, or order emission.
        """
        normalized_day = self._normalize_day(day)
        if not enabled:
            return self._hook_result(
                hook_name="intraday_summary",
                enabled=False,
                status="disabled",
                reason="reporter_hook_disabled",
                day=normalized_day,
            )
        if not emit_reports:
            return self._hook_result(
                hook_name="intraday_summary",
                enabled=True,
                status="reserved",
                reason="report_generation_disabled",
                day=normalized_day,
            )
        summary = self.generate_operator_summary(
            event_log_path=event_log_path,
            report_dir=reports_root,
            day=normalized_day,
        )
        return self._hook_result(
            hook_name="intraday_summary",
            enabled=True,
            status="generated",
            executed=True,
            reason="operator_summary_generated",
            day=normalized_day,
            report_type=summary.report_type,
            output_paths=dict(summary.output_paths),
            warnings=list(summary.warnings),
            data_freshness=dict(summary.data_freshness),
            generated_reports=[summary.report_type],
        )

    def maybe_generate_eod_reports(
        self,
        *,
        enabled: bool = False,
        emit_reports: bool = False,
        event_log_path: str | Path = "data/logs/events.jsonl",
        reports_root: str | Path = "reports",
        day: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Optional commander hook for end-of-day reporting.

        Default behavior is a reserved no-op. Full orchestration remains a later
        step so Commander runtime semantics stay unchanged.
        """
        normalized_day = self._normalize_day(day)
        if not enabled:
            return self._hook_result(
                hook_name="eod_reports",
                enabled=False,
                status="disabled",
                reason="reporter_hook_disabled",
                day=normalized_day,
            )
        if not emit_reports:
            return self._hook_result(
                hook_name="eod_reports",
                enabled=True,
                status="reserved",
                reason="report_generation_disabled",
                day=normalized_day,
            )
        generated = [
            self.generate_daily_report(event_log_path=event_log_path, reports_root=reports_root, day=normalized_day),
            self.generate_operator_summary(event_log_path=event_log_path, report_dir=reports_root, day=normalized_day),
            self.generate_metrics_report(event_log_path=event_log_path, report_dir=self._path(reports_root) / "metrics", day=normalized_day),
        ]
        output_paths: Dict[str, str] = {}
        warnings: List[str] = []
        for item in generated:
            prefix = str(item.report_type or "")
            if item.report_json_path:
                output_paths[f"{prefix}_json"] = item.report_json_path
            if item.report_md_path:
                output_paths[f"{prefix}_md"] = item.report_md_path
            warnings.extend(list(item.warnings))
        return self._hook_result(
            hook_name="eod_reports",
            enabled=True,
            status="generated",
            executed=True,
            reason="eod_reports_generated",
            day=normalized_day,
            report_type="eod_bundle",
            output_paths=output_paths,
            warnings=warnings,
            generated_reports=[item.report_type for item in generated],
        )

    def maybe_generate_strategist_feedback(
        self,
        *,
        enabled: bool = False,
        day: Optional[str] = None,
        reports_root: str | Path = "reports",
    ) -> Dict[str, Any]:
        """Reserved strategist-feedback hook.

        Reporter may summarize and package insight for future Strategist
        consumption, but this hook has no decision authority and stays
        placeholder-only in this phase.
        """
        normalized_day = self._normalize_day(day)
        if not enabled:
            return self._hook_result(
                hook_name="strategist_feedback",
                enabled=False,
                status="disabled",
                reason="reporter_hook_disabled",
                day=normalized_day,
            )
        return self._hook_result(
            hook_name="strategist_feedback",
            enabled=True,
            status="generated",
            executed=True,
            reason="strategist_feedback_generated",
            day=normalized_day,
            strategist_feedback_packet=build_strategist_feedback_packet(
                mode="strategist_feedback",
                payload={"day": normalized_day},
                reports_root=reports_root,
                day=normalized_day,
            ),
        )


def _normalize_trade_reporter_policy(policy: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    cfg = dict(policy or {})
    execution_profile = cfg.get("execution_profile") if isinstance(cfg.get("execution_profile"), dict) else {}
    return {
        "model": str(cfg.get("model") or "").strip(),
        "execution_profile": dict(execution_profile),
    }


def _validate_trade_read_model(trade_model: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(trade_model, dict) or not trade_model:
        return {"ok": False, "reason": "trade_read_model_missing"}
    facts = trade_model.get("facts") if isinstance(trade_model.get("facts"), dict) else {}
    provenance = trade_model.get("provenance") if isinstance(trade_model.get("provenance"), dict) else {}
    if not facts:
        return {"ok": False, "reason": "trade_read_model_facts_missing"}
    if not provenance:
        return {"ok": False, "reason": "trade_read_model_provenance_missing"}
    return {"ok": True, "reason": ""}


def run_reporter_agent(trade_dir: str, policy: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """R2 entrypoint: trade-level reporter agent output.

    This function is additive and does not alter runtime trading flow.
    """
    from libs.reporting.trade_read_model import build_trade_read_model
    from libs.reporting.fact_narrative_report import build_separated_report

    trade_root = Path(str(trade_dir))
    cfg = _normalize_trade_reporter_policy(policy)

    try:
        trade_model = build_trade_read_model(str(trade_root))
    except Exception as exc:
        return {
            "metadata": {
                "trade_id": "",
                "symbol": "",
                "trade_dir": str(trade_root),
                "generated_by": "reporter_agent_v1",
            },
            "facts": {},
            "provenance": {},
            "narrative": {
                "status": "error",
                "source": "llm",
                "based_on": "fact_payload",
                "reason": "trade_read_model_exception",
                "error": str(exc),
            },
            "status": "degraded",
        }

    validation = _validate_trade_read_model(trade_model)
    if not bool(validation.get("ok")):
        return {
            "metadata": {
                "trade_id": str(trade_model.get("trade_id") or ""),
                "symbol": str(trade_model.get("symbol") or ""),
                "trade_dir": str(trade_root),
                "generated_by": "reporter_agent_v1",
            },
            "facts": dict(trade_model.get("facts") or {}),
            "provenance": dict(trade_model.get("provenance") or {}),
            "context": dict(trade_model.get("context") or {}),
            "narrative": {
                "status": "skipped",
                "source": "llm",
                "based_on": "fact_payload",
                "reason": str(validation.get("reason") or "invalid_trade_read_model"),
                "llm_call_skipped": True,
            },
            "status": "degraded",
        }

    separated = build_separated_report(
        trade_model=trade_model,
        model=cfg["model"] or None,
        execution_profile=cfg["execution_profile"] or None,
    )
    narrative = separated.get("narrative") if isinstance(separated.get("narrative"), dict) else {}
    facts = trade_model.get("facts") if isinstance(trade_model.get("facts"), dict) else {}
    provenance = trade_model.get("provenance") if isinstance(trade_model.get("provenance"), dict) else {}
    context = trade_model.get("context") if isinstance(trade_model.get("context"), dict) else {}

    return {
        "metadata": {
            "trade_id": str(facts.get("trade_id") or trade_model.get("trade_id") or ""),
            "symbol": str(facts.get("symbol") or trade_model.get("symbol") or ""),
            "trade_dir": str(trade_root),
            "generated_by": "reporter_agent_v1",
        },
        "facts": dict(facts),
        "provenance": dict(provenance),
        "context": dict(context),
        "narrative": dict(narrative),
        "status": "ok" if str(narrative.get("status") or "").strip().lower() in {"ok", "dry_run", "skipped"} else "degraded",
    }
