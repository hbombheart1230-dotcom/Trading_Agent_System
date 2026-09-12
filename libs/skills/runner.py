from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_request_builder import ApiRequestBuilder, PrepareResult, PreparedRequest
from libs.core.event_logger import EventLogger
from libs.core.symbols import normalize_symbol
from libs.execution.executors import get_executor
from libs.execution.guards.broker_mutation import is_mutation_api_id
from libs.execution.guards.unknown_quarantine import (
    evaluate_unknown_quarantine_guard,
    quarantine_symbol_for_unknown_outcome,
)
from libs.core.settings import Settings

from .registry import SkillRegistry, SkillSpec
from .rules import DefaultRuleEngine
from .dto import RawDTO
from . import dto_extractors as ex


@dataclass(frozen=True)
class SkillRunResult:
    action: str  # 'ready' or 'ask' or 'error'
    skill: str
    outputs: str
    data: Any
    missing: List[str]
    question: str
    meta: Dict[str, Any]


def _render_template(v: Any, args: Dict[str, Any]) -> Any:
    if not isinstance(v, str):
        return v
    s = v
    # simple "{key}" replacement
    for k, val in args.items():
        s = s.replace("{" + k + "}", str(val))
    # normalize placeholders left
    if "{" in s and "}" in s:
        # unresolved placeholder -> empty
        s = ""
    return s


class CompositeSkillRunner:
    """Runs Composite Skills described in YAML, using api_catalog.jsonl.

    Core rule:
      - Caller supplies *content only* (args). No api_id/path/mrkt_tp knowledge required.
      - YAML provides defaults + mapping; builder enforces required params.
    """

    @classmethod
    def from_env(
        cls,
        *,
        settings: Optional[Settings] = None,
        catalog_path: Optional[str] = None,
        skills_dir: Optional[str] = None,
        event_log_path: Optional[str] = None,
    ) -> "CompositeSkillRunner":
        """Construct a runner using environment defaults.

        This method exists for consistency across the codebase and tests.
        """
        s = settings or Settings.from_env()
        return cls(
            settings=s,
            catalog_path=catalog_path or os.getenv("KIWOOM_API_CATALOG_JSONL", "data/specs/api_catalog.jsonl"),
            skills_dir=skills_dir or os.getenv("SKILLS_DIR", "config/skills"),
            event_log_path=event_log_path or os.getenv("EVENT_LOG_PATH", "data/logs/events.jsonl"),
        )

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        catalog_path: Optional[str] = None,
        skills_dir: str = "config/skills",
        event_log_path: str = "data/logs/events.jsonl",
    ):
        self.s = settings or Settings.from_env()
        self.catalog_path = catalog_path or os.getenv("KIWOOM_API_CATALOG_JSONL", "data/specs/api_catalog.jsonl")
        self.catalog = ApiCatalog.load(self.catalog_path)
        self.registry = SkillRegistry(skills_dir).load()
        self.builder = ApiRequestBuilder()
        self.executor = get_executor(settings=self.s, catalog=self.catalog)
        self.rules = DefaultRuleEngine()
        self.events = EventLogger(event_log_path)

    def run(self, *, run_id: str, skill: str, args: Dict[str, Any]) -> SkillRunResult:
        spec: SkillSpec = self.registry.get(skill)
        payloads: List[Dict[str, Any]] = []
        step_meta: List[Dict[str, Any]] = []

        # allow dynamic api_id switch for order.place by side
        args = dict(args or {})
        if skill == "order.place":
            side = (args.get("side") or "buy").lower()
            if side == "sell":
                # override first step api_id
                # NOTE: kt10001 = sell
                spec = self._clone_spec_override_first_api(spec, "kt10001")

        for idx, step in enumerate(spec.steps):
            api_id = step.api_id
            api_spec = self.catalog.get(api_id)

            # defaults + mapped args
            ctx: Dict[str, Any] = {}
            ctx.update({k: _render_template(v, args) for k, v in (step.defaults or {}).items()})
            ctx.update({k: _render_template(v, args) for k, v in (step.map or {}).items()})
            # also allow passing raw args (non-mapped), but mapped/defaults win
            for k, v in args.items():
                ctx.setdefault(k, v)

            # inject global defaults (keeps YAML minimal)
            ctx = self.rules.apply(api_id, ctx)

            # normalize common: price "" for market order
            if api_id in ("kt10000", "kt10001"):
                trde_tp = str(ctx.get("trde_tp") or "")
                if trde_tp == "3":  # market
                    # kiwoom expects ord_uv empty
                    ctx["ord_uv"] = ""

            prep: PrepareResult = self.builder.prepare(api_spec, ctx)
            if prep.action != "ready" or not prep.request:
                self.events.log(run_id=run_id, stage="skill_prepare", event="ask", payload={
                    "skill": skill, "api_id": api_id, "missing": prep.missing, "reason": prep.reason
                })
                return SkillRunResult(
                    action="ask",
                    skill=skill,
                    outputs=spec.outputs,
                    data=None,
                    missing=prep.missing,
                    question=prep.question,
                    meta={"api_id": api_id, "step": idx},
                )

            # Phase 1 Step 5B Fix 3 (HIGH1): this is a second, independent
            # live mutation path (reached via ToolFacade.order_execute /
            # ExecutorAgent.execute_order, both of which call this method)
            # that previously never checked or wrote the durable UNKNOWN
            # quarantine state graphs/nodes/execute_from_packet.py's guard
            # chain uses -- so a symbol quarantined by one path was not
            # respected by the other, and an UNKNOWN outcome from *this*
            # path never quarantined anything, letting the same logical
            # mutation be resubmitted. Scoped strictly to mutation api_ids
            # (kt10000/kt10001/kt10002/kt10003); read/token steps are
            # unaffected.
            is_mutation = is_mutation_api_id(api_id)

            if is_mutation:
                # Step5C Fix5 (HIGH1): mutation detection must decide the
                # authority boundary BEFORE symbol normalization is even
                # attempted -- Codex's exact reproduction was `BUY 0082N0`:
                # is_mutation_api_id() was True, normalize_symbol() returned
                # "" for the malformed code, and the OLD `if is_mutation and
                # mutation_symbol:` guard treated an empty mutation_symbol as
                # "not a protected mutation", falling through to the plain
                # `self.executor.execute(prep.request)` branch with zero
                # ownership/quarantine/physical-claim protection at all
                # (broker calls == 1, expected 0). A mutation whose symbol
                # cannot be canonicalized is not "less of a mutation" -- it
                # is an invalid one, and must fail closed, never reach the
                # generic executor path.
                mutation_symbol = normalize_symbol(ctx.get("stk_cd") or args.get("symbol"))
                if not mutation_symbol:
                    self.events.log(run_id=run_id, stage="skill_execute", event="ownership_claim_denied", payload={
                        "skill": skill, "api_id": api_id, "step": idx,
                        "raw_symbol": ctx.get("stk_cd") or args.get("symbol"),
                        "reason": "INVALID_SYMBOL",
                    })
                    return SkillRunResult(
                        action="error",
                        skill=skill,
                        outputs=spec.outputs,
                        data=None,
                        missing=[],
                        question="",
                        meta={
                            "api_id": api_id,
                            "step": idx,
                            "raw_symbol": ctx.get("stk_cd") or args.get("symbol"),
                            "blocked_reason": "INVALID_SYMBOL",
                            "broker_api_called": False,
                        },
                    )

                guard_allowed, guard_reason, guard_details = evaluate_unknown_quarantine_guard(mutation_symbol)
                if not guard_allowed:
                    self.events.log(run_id=run_id, stage="skill_execute", event="quarantine_block", payload={
                        "skill": skill, "api_id": api_id, "step": idx, "symbol": mutation_symbol,
                        "reason": guard_reason, **guard_details,
                    })
                    return SkillRunResult(
                        action="error",
                        skill=skill,
                        outputs=spec.outputs,
                        data=None,
                        missing=[],
                        question="",
                        meta={
                            "api_id": api_id,
                            "step": idx,
                            "blocked_reason": guard_reason,
                            "symbol": mutation_symbol,
                            "quarantine": guard_details,
                        },
                    )

            self.events.log(run_id=run_id, stage="skill_execute", event="call", payload={
                "skill": skill, "api_id": api_id, "step": idx, "path": prep.request.path
            })

            # Step5C Fix2 (HIGH1): every real broker mutation reachable
            # through this runner (order.place -> kt10000/kt10001 today)
            # goes through libs/execution/intent_execution_owner.py's single
            # canonical claim-dispatch-finish sequence, unconditionally --
            # there is deliberately no "state already reads EXECUTING, some
            # other caller (e.g. ApprovalService) must have legitimately
            # claimed it, so just dispatch" shortcut. Codex's independent
            # audit reproduced exactly that shortcut allowing two concurrent
            # runner invocations to both see EXECUTING and both call the
            # executor (broker calls == 2, not <= 1) -- a state VALUE is not
            # ownership evidence; only winning the atomic CAS inside
            # execute_owned_order is. ApprovalService.approve() (see
            # libs/approval/service.py) no longer performs its own separate
            # approved->executing transition for this reason -- this is now
            # the only call site that ever claims execution.
            #
            # Fix2 (item 16): a real mutation also requires the caller to
            # supply a canonical intent_id established upstream (at
            # OrderIntent creation, e.g. TwoPhaseSupervisor.create_intent or
            # decide_trade.py) -- this runner does not invent one. A caller
            # reaching this point with no intent_id at all is a caller bug,
            # not a case to paper over with a freshly-hashed identity.
            #
            # Step5C Fix5 (HIGH1, item 2): is_mutation alone now decides
            # whether this branch or the plain generic-executor branch below
            # runs -- there is no secondary "and mutation_symbol truthy"
            # condition left anywhere on this path (mutation_symbol is
            # already guaranteed valid by the fail-closed check above, or
            # this line is never reached for this api_id at all).
            if is_mutation:
                owner_intent_id = str(args.get("intent_id") or "").strip()
                if not owner_intent_id:
                    self.events.log(run_id=run_id, stage="skill_execute", event="ownership_claim_denied", payload={
                        "skill": skill, "api_id": api_id, "step": idx, "symbol": mutation_symbol,
                        "reason": "missing_canonical_intent_identity",
                    })
                    return SkillRunResult(
                        action="error",
                        skill=skill,
                        outputs=spec.outputs,
                        data=None,
                        missing=[],
                        question="",
                        meta={
                            "api_id": api_id,
                            "step": idx,
                            "symbol": mutation_symbol,
                            "blocked_reason": "missing_canonical_intent_identity",
                            "broker_api_called": False,
                        },
                    )
                from libs.execution.intent_execution_owner import execute_owned_order
                owner_order = {
                    "intent_id": owner_intent_id,
                    "action": str(args.get("side") or "").upper() or "BUY",
                    "symbol": mutation_symbol,
                    # The caller's own typed args (not the HTTP-body ctx,
                    # which templates everything to str) so the identity
                    # fingerprint matches what an automated-path caller
                    # building the same real-world order would hash.
                    "qty": args.get("qty"),
                    "price": ctx.get("ord_uv") if str(ctx.get("trde_tp") or "") != "3" else args.get("price"),
                    "order_type": args.get("order_type"),
                    "trde_tp": ctx.get("trde_tp"),
                }
                dispatch: Dict[str, Any] = {}
                def _capture_dispatch(result, _dispatch=dispatch):
                    _dispatch["result"] = result
                    if result is None:
                        return {"broker_outcome": "NOT_SENT"}
                    # Same fallback convention as execute_order.py's own
                    # normalize_legacy: prefer the executor's own
                    # broker_outcome meta, else derive ACCEPTED/REJECTED
                    # from response.ok for an executor (e.g.
                    # MockExecutor) that doesn't emit one. This is only
                    # used to record the correct terminal state in the
                    # canonical intent store below -- it does not
                    # replace the broker_outcome this function's
                    # existing quarantine check reads from res.meta.
                    outcome = str((getattr(result, "meta", None) or {}).get("broker_outcome") or "").strip().upper()
                    if not outcome:
                        ok = bool(getattr(getattr(result, "response", None), "ok", False))
                        outcome = "ACCEPTED" if ok else "REJECTED"
                    return {"broker_outcome": outcome}
                owned = execute_owned_order(
                    state={"run_id": run_id}, order=owner_order, request=prep.request,
                    executor=self.executor, normalize=_capture_dispatch,
                )
                if not owned.get("intent_claim", {}).get("claimed"):
                    self.events.log(run_id=run_id, stage="skill_execute", event="ownership_claim_denied", payload={
                        "skill": skill, "api_id": api_id, "step": idx, "symbol": mutation_symbol,
                        "intent_id": owner_intent_id, "reason": owned.get("reason"),
                        "physical_order_key": owned.get("physical_order_key"),
                    })
                    return SkillRunResult(
                        action="error",
                        skill=skill,
                        outputs=spec.outputs,
                        data=None,
                        missing=[],
                        question="",
                        meta={
                            "api_id": api_id,
                            "step": idx,
                            "symbol": mutation_symbol,
                            "intent_id": owner_intent_id,
                            "blocked_reason": owned.get("reason") or "execution_ownership_denied",
                            "physical_order_key": owned.get("physical_order_key"),
                            "broker_api_called": False,
                        },
                    )
                res = dispatch["result"]
            else:
                res = self.executor.execute(prep.request)  # real/mock governed by env
            if is_mutation:
                broker_outcome = str((res.meta or {}).get("broker_outcome") or "").strip().upper()
                if broker_outcome == "UNKNOWN":
                    quarantine_symbol_for_unknown_outcome(
                        symbol=mutation_symbol,
                        operation=str(args.get("side") or "").upper() or "MUTATION",
                        now_epoch=int(time.time()),
                        run_id=run_id,
                        exception_type=str((res.meta or {}).get("exception_type") or ""),
                        reason="broker_outcome_unknown",
                    )
            payload = res.response.payload if res and res.response else {}
            payloads.append(payload)
            step_meta.append({"api_id": api_id, "url": (res.meta or {}).get("url")})

        # DTO selection
        dto = self._to_dto(spec.outputs, args, payloads, {"steps": step_meta})
        self.events.log(run_id=run_id, stage="skill_result", event="ok", payload={
            "skill": skill, "outputs": spec.outputs
        })
        return SkillRunResult(
            action="ready",
            skill=skill,
            outputs=spec.outputs,
            data=dto,
            missing=[],
            question="",
            meta={"steps": step_meta},
        )

    def _clone_spec_override_first_api(self, spec: SkillSpec, api_id: str) -> SkillSpec:
        from .registry import SkillStep, SkillSpec as SS
        steps = list(spec.steps)
        steps[0] = SkillStep(api_id=api_id, defaults=steps[0].defaults, map=steps[0].map)
        return SS(skill=spec.skill, description=spec.description, outputs=spec.outputs, steps=steps)

    def _to_dto(self, outputs: str, args: Dict[str, Any], payloads: List[Dict[str, Any]], meta: Dict[str, Any]) -> Any:
        outputs = (outputs or "").strip()
        if outputs == "QuoteDTO":
            return ex.extract_quote(str(args.get("symbol") or ""), payloads[0] if payloads else {})
        if outputs == "MinuteOHLCVDTO":
            return ex.extract_minute_ohlcv(
                str(args.get("symbol") or ""),
                int(args.get("timeframe_minutes") or 1),
                payloads[0] if payloads else {},
            )
        if outputs == "OrderPlaceDTO":
            return ex.extract_order_place(str(args.get("side") or "buy"), str(args.get("symbol") or ""), payloads[0] if payloads else {})
        if outputs == "OrderStatusDTO":
            return ex.extract_order_status(str(args.get("ord_no") or ""), payloads)
        if outputs == "AccountOrdersDTO":
            return ex.extract_account_orders(payloads[0] if payloads else {})
        # fallback
        return ex.as_raw(payloads, meta)
