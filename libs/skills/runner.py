from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional

from libs.catalog.api_catalog import ApiCatalog
from libs.catalog.api_request_builder import ApiRequestBuilder, PrepareResult, PreparedRequest
from libs.core.event_logger import EventLogger
from libs.execution.executors import get_executor
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

            self.events.log(run_id=run_id, stage="skill_execute", event="call", payload={
                "skill": skill, "api_id": api_id, "step": idx, "path": prep.request.path
            })

            res = self.executor.execute(prep.request)  # real/mock governed by env
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
        if outputs == "OrderPlaceDTO":
            return ex.extract_order_place(str(args.get("side") or "buy"), str(args.get("symbol") or ""), payloads[0] if payloads else {})
        if outputs == "OrderStatusDTO":
            return ex.extract_order_status(str(args.get("ord_no") or ""), payloads)
        if outputs == "AccountOrdersDTO":
            return ex.extract_account_orders(payloads[0] if payloads else {})
        # fallback
        return ex.as_raw(payloads, meta)
