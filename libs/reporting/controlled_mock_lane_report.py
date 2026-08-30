from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


LANE_LABELS = {
    "BTC_WOORI": "Q12 BTC-우기투",
    "Q10_SEMICONDUCTOR": "Q10 반도체 선행시장",
    "Q10_INDEX": "Q10 한국지수 선행시장",
}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        row = _mapping(value)
        if row:
            return row
    return {}


def _position_strategy(state: Mapping[str, Any], symbol: str) -> dict[str, Any]:
    persisted = _mapping(state.get("persisted_state"))
    contexts = _mapping(persisted.get("position_strategy_context"))
    row = _mapping(contexts.get(symbol))
    return _mapping(row.get("output"))


def _ledger_row(*, root: Path, day: str, symbol: str) -> dict[str, Any]:
    path = root / "data" / "logs" / "controlled_mock_lanes" / day / "lane_submissions.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    rows = payload.get("submissions") if isinstance(payload, Mapping) else []
    matches = [
        dict(row)
        for row in list(rows or [])
        if isinstance(row, Mapping) and _text(row.get("symbol")) == symbol
    ]
    return matches[-1] if matches else {}


def build_controlled_lane_report_surface(
    state: Mapping[str, Any], *, day: str = "", root: Path | str | None = None
) -> dict[str, Any]:
    """Extract immutable entry evidence for a controlled mock validation order."""

    execution = _mapping(state.get("execution"))
    order = _mapping(execution.get("order"))
    meta = _mapping(order.get("meta"))
    lane = _mapping(meta.get("controlled_mock_lane"))
    symbol = _text(order.get("symbol") or execution.get("symbol") or state.get("symbol"))
    strategy = _mapping(meta.get("position_strategy_snapshot"))
    if not strategy and symbol:
        strategy = _position_strategy(state, symbol)
    if not lane and strategy.get("controlled_mock_lane") and day and root is not None:
        lane = _ledger_row(root=Path(root), day=day, symbol=symbol)
    if not lane or not strategy.get("controlled_mock_lane"):
        return {}
    lane_id = _text(lane.get("lane_id"))
    return {
        "schema_version": "controlled_mock_lane_report.v1",
        "lane_id": lane_id,
        "lane_label": LANE_LABELS.get(lane_id, lane_id),
        "symbol": _text(lane.get("symbol") or symbol),
        "signal_id": _text(lane.get("signal_id")),
        "signal_epoch": lane.get("signal_epoch"),
        "score": lane.get("score"),
        "evidence": _mapping(lane.get("evidence")),
        "daily_limit": lane.get("daily_limit"),
        "reservation": _mapping(lane.get("reservation")),
        "strategy_horizon": _text(strategy.get("strategy_horizon")),
        "expected_hold_window": _mapping(strategy.get("expected_hold_window")),
        "llm_used": bool(strategy.get("llm_used")),
        "stage3_horizon_review_allowed": bool(
            strategy.get("horizon_revision_allowed", True)
        ),
        "selection_authority": "deterministic_independent_lane",
        "execution_scope": "kiwoom_mock_only",
    }


def controlled_lane_surface_from_report(report: Mapping[str, Any]) -> dict[str, Any]:
    fact_payload = _mapping(report.get("fact_payload"))
    trade = _mapping(fact_payload.get("trade"))
    lifecycle = _first_mapping(
        report.get("trade_lifecycle"),
        report.get("lifecycle"),
        trade.get("trade_lifecycle"),
        trade.get("lifecycle"),
    )
    entry = _mapping(lifecycle.get("entry"))
    lifecycle_bundle = _first_mapping(
        report.get("lifecycle_bundle"), trade.get("lifecycle_bundle")
    )
    bundle_lifecycle = _mapping(lifecycle_bundle.get("lifecycle"))
    bundle_entry = _mapping(bundle_lifecycle.get("entry"))
    return _first_mapping(
        report.get("controlled_mock_lane"),
        trade.get("controlled_mock_lane"),
        lifecycle_bundle.get("controlled_mock_lane"),
        entry.get("controlled_mock_lane"),
        bundle_entry.get("controlled_mock_lane"),
    )


def attach_controlled_lane_report_surface(
    report: dict[str, Any], story_input: Mapping[str, Any]
) -> dict[str, Any]:
    surface = _first_mapping(
        story_input.get("controlled_mock_lane"),
        _mapping(story_input.get("trade_lifecycle")).get("controlled_mock_lane"),
        _mapping(_mapping(story_input.get("trade_lifecycle")).get("entry")).get(
            "controlled_mock_lane"
        ),
        _mapping(story_input.get("lifecycle_bundle")).get("controlled_mock_lane"),
    )
    if surface:
        report["controlled_mock_lane"] = surface
        fact_payload = _mapping(report.get("fact_payload"))
        trade = _mapping(fact_payload.get("trade"))
        if trade:
            trade.setdefault("controlled_mock_lane", surface)
            fact_payload["trade"] = trade
            report["fact_payload"] = fact_payload
    return report


def render_controlled_lane_report_lines(report: Mapping[str, Any]) -> list[str]:
    surface = controlled_lane_surface_from_report(report)
    if not surface:
        return []
    evidence = _mapping(surface.get("evidence"))
    window = _mapping(surface.get("expected_hold_window"))
    lines = [
        f"* 실행 레인: **{_text(surface.get('lane_label')) or _text(surface.get('lane_id'))}**",
        f"* 신호 ID: `{_text(surface.get('signal_id')) or '-'}`",
        f"* 선택 권한: {_text(surface.get('selection_authority')) or 'deterministic_independent_lane'}",
        f"* LLM 사용: {'예' if surface.get('llm_used') else '아니오'}",
    ]
    if surface.get("score") not in (None, ""):
        lines.append(f"* 신호 점수: {surface.get('score')}")
    if evidence:
        evidence_text = " / ".join(
            f"{key}={value}"
            for key, value in evidence.items()
            if value not in (None, "", [], {})
        )
        if evidence_text:
            lines.append(f"* 고정 가설 근거: {evidence_text}")
    if window:
        lines.append(
            "* 고정 보유 구간: "
            f"최소 {window.get('min_sec', '-')}초 / 목표 {window.get('target_sec', '-')}초 / "
            f"최대 {window.get('max_sec', '-')}초"
        )
    if surface.get("stage3_horizon_review_allowed"):
        lines.append("* R3 연결: 허용됨. 3차 전략가의 보유기간 재검토를 적용할 수 있습니다.")
    else:
        lines.append(
            "* R3 연결: 차단됨. 이 통제 레인은 고정 horizon 비교를 위해 3차 전략가의 "
            "보유기간 변경을 적용하지 않습니다."
        )
    lines.append("* 주문 범위: 키움 모의투자 검증 전용")
    return lines


__all__ = [
    "attach_controlled_lane_report_surface",
    "build_controlled_lane_report_surface",
    "controlled_lane_surface_from_report",
    "render_controlled_lane_report_lines",
]
