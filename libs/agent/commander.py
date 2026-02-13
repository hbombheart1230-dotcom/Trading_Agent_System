from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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

        plan = self.strategist.make_plan(context=context)
        scan = self.scanner.scan(plan=plan, context=context)

        intent = scan.get("intent") if isinstance(scan, dict) else None
        execution: Optional[Dict[str, Any]] = None
        if intent:
            execution = self.executor.submit(
                intent=intent,
                approval_mode=approval_mode,
                execution_enabled=execution_enabled,
            )

        self.monitor.update(plan=plan, scan=scan, execution=execution, context=context)
        report = self.reporter.build_report(plan=plan, scan=scan, execution=execution, context=context)

        return CommandResult(plan=plan, scan=scan, intent=intent, execution=execution, report=report)
