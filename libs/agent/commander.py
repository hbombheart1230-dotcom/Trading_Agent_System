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
    run_id: str
    decisions: List[Dict[str, Any]]
    executions: List[Dict[str, Any]]
    report: Optional[Dict[str, Any]] = None


class Commander:
    """Top-level orchestration for the Agent Layer (M15).

    Commander does NOT call broker APIs directly.
    It delegates execution to AgentExecutor, which then calls Execution Layer.
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
        run_id: str,
        context: Dict[str, Any],
        approval_mode: str = "manual",
        execution_enabled: bool = False,
    ) -> CommandResult:
        """Execute one full cycle.

        context: free-form runtime inputs (market snapshot, constraints, etc.)
        """
        # 1) strategy -> candidate universe / intent drafts
        plan = self.strategist.plan(context=context)

        # 2) scan -> filter + produce concrete intents
        intents = self.scanner.scan(plan=plan, context=context)

        # 3) execute (two-phase / approval-aware)
        decisions: List[Dict[str, Any]] = []
        executions: List[Dict[str, Any]] = []
        for intent in intents:
            res = self.executor.submit(intent=intent, approval_mode=approval_mode, execution_enabled=execution_enabled)
            # normalize outputs
            if isinstance(res, dict):
                if "decision" in res:
                    decisions.append(res["decision"])
                else:
                    decisions.append(res)
                if "execution" in res:
                    executions.append(res["execution"])

        # 4) monitor -> update state (optional)
        self.monitor.update(intents=intents, decisions=decisions, executions=executions, context=context)

        # 5) reporter -> summarize
        report = self.reporter.build(run_id=run_id, context=context, plan=plan, intents=intents, decisions=decisions, executions=executions)

        return CommandResult(run_id=run_id, decisions=decisions, executions=executions, report=report)
