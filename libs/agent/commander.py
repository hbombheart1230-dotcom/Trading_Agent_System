from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import uuid

from libs.agent.strategist import Strategist
from libs.agent.scanner import Scanner
from libs.agent.monitor import Monitor
from libs.agent.reporter import Reporter
from libs.agent.executor import AgentExecutor


@dataclass
class CommandResult:
    """High-level result returned by Commander."""

    plan: Dict[str, Any]
    scan: Dict[str, Any]
    intent: Optional[Dict[str, Any]]
    execution: Optional[Dict[str, Any]]
    report: Dict[str, Any]


class Commander:
    """Orchestrate one agent cycle (M15).

    Strategist -> Scanner -> (optional) Executor -> Monitor -> Reporter
    """

    def __init__(
        self,
        *,
        strategist: Strategist,
        scanner: Scanner,
        monitor: Monitor,
        reporter: Reporter,
        executor: AgentExecutor,
    ):
        self.strategist = strategist
        self.scanner = scanner
        self.monitor = monitor
        self.reporter = reporter
        self.executor = executor

    def run(
        self,
        *,
        context: Optional[Dict[str, Any]] = None,
        approval_mode: str = "manual",
        execution_enabled: bool = False,
    ) -> CommandResult:
        context = context or {}

        # Strategist method name compatibility:
        # - preferred: plan(...)
        # - legacy: make_plan(...)
        if hasattr(self.strategist, "plan"):
            plan_obj = self.strategist.plan(context=context)  # type: ignore[attr-defined]
        else:
            plan_obj = self.strategist.make_plan(context=context)  # type: ignore[attr-defined]

        scan_obj = self.scanner.scan(plan=plan_obj, context=context)

        # Scanner contract compatibility:
        # - list[intent]
        # - {"intents":[...]} or {"intent": {...}}
        if isinstance(scan_obj, list):
            intents = [x for x in scan_obj if isinstance(x, dict)]
            scan = {"intents": intents}
        elif isinstance(scan_obj, dict):
            scan = dict(scan_obj)
            if isinstance(scan.get("intents"), list):
                intents = [x for x in scan["intents"] if isinstance(x, dict)]
            elif isinstance(scan.get("intent"), dict):
                intents = [scan["intent"]]
            else:
                intents = []
                if isinstance(scan.get("intent"), list):
                    intents = [x for x in scan["intent"] if isinstance(x, dict)]
            scan["intents"] = intents
        else:
            intents = []
            scan = {"intents": intents}

        intent = intents[0] if intents else None
        execution: Optional[Dict[str, Any]] = None
        if intent:
            execution = self.executor.submit(
                intent=intent,
                approval_mode=approval_mode,
                execution_enabled=execution_enabled,
            )

        decisions: List[Dict[str, Any]] = []
        if isinstance(execution, dict):
            d = execution.get("decision")
            if isinstance(d, dict):
                decisions.append(d)

        # Monitor contract compatibility:
        # - current: update(intents, decisions, executions, context)
        # - legacy : update(plan=..., scan=..., execution=..., context=...)
        try:
            self.monitor.update(
                intents=intents,
                decisions=decisions,
                executions=([execution] if execution else []),
                context=context,
            )
        except TypeError:
            self.monitor.update(plan=plan_obj, scan=scan, execution=execution, context=context)  # type: ignore[arg-type]

        run_id = str(context.get("run_id") or uuid.uuid4().hex)

        # Reporter contract compatibility:
        # - current: build(run_id, context, plan, intents, decisions, executions)
        # - legacy : build_report(plan=..., scan=..., execution=..., context=...)
        try:
            report = self.reporter.build(
                run_id=run_id,
                context=context,
                plan=plan_obj,
                intents=intents,
                decisions=decisions,
                executions=([execution] if execution else []),
            )
        except TypeError:
            report = self.reporter.build_report(plan=plan_obj, scan=scan, execution=execution, context=context)  # type: ignore[arg-type]

        # Keep CommandResult contracts as dict-shaped payloads.
        plan = plan_obj if isinstance(plan_obj, dict) else dict(getattr(plan_obj, "__dict__", {}))
        return CommandResult(plan=plan, scan=scan, intent=intent, execution=execution, report=report)
