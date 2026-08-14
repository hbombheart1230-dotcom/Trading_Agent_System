from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from ..models.common import AvailabilityStatus
from ..models.llm_operations import (
    LlmLatencySummary,
    LlmRecentCall,
    LlmRoleUsage,
    LlmStageUsage,
    LlmTokenUsage,
)
from .llm_role_catalog import ROLE_CATALOG

SUCCESS_STATES = {"ok", "repaired", "salvaged", "success"}
EARLIEST_UTC = datetime(1970, 1, 1, tzinfo=UTC)


def success_count(calls: list[dict[str, Any]]) -> int:
    return sum(is_success(row.get("status")) for row in calls)


def latest_call_at(calls: list[dict[str, Any]]) -> datetime | None:
    values = [as_datetime(row.get("saved_at")) for row in calls]
    return max((value for value in values if value is not None), default=None)


def build_latency_summary(
    recent: list[LlmRecentCall],
    total_calls: int,
    truncated: bool,
) -> LlmLatencySummary:
    values = sorted(call.latency_ms for call in recent if call.latency_ms is not None)
    coverage = min(1.0, len(values) / total_calls) if total_calls else None
    if not values:
        status = AvailabilityStatus.UNAVAILABLE
    elif truncated or len(values) != total_calls:
        status = AvailabilityStatus.PARTIAL
    else:
        status = AvailabilityStatus.AVAILABLE
    index = max(0, min(len(values) - 1, int(len(values) * 0.95 + 0.9999) - 1)) if values else 0
    return LlmLatencySummary(
        status=status,
        observed_count=len(values),
        average_ms=sum(values) / len(values) if values else None,
        p95_ms=values[index] if values else None,
        maximum_ms=max(values) if values else None,
        coverage=coverage,
        recent_window_only=truncated or len(values) != total_calls,
    )


def build_token_summary(
    recent: list[LlmRecentCall],
    total_calls: int,
) -> LlmTokenUsage:
    covered = [call for call in recent if call.total_tokens is not None]
    if covered:
        status = (
            AvailabilityStatus.AVAILABLE
            if len(covered) == total_calls
            else AvailabilityStatus.PARTIAL
        )
        prompt = [call.prompt_tokens for call in covered if call.prompt_tokens is not None]
        completion = [call.completion_tokens for call in covered if call.completion_tokens is not None]
        costs = [call.estimated_cost_usd for call in covered if call.estimated_cost_usd is not None]
        return LlmTokenUsage(
            status=status,
            prompt_tokens=sum(prompt) if prompt else None,
            completion_tokens=sum(completion) if completion else None,
            total_tokens=sum(call.total_tokens or 0 for call in covered),
            estimated_cost_usd=sum(costs) if costs else None,
            reason=(
                None
                if status == AvailabilityStatus.AVAILABLE
                else "Token usage is available only for part of the bounded event window"
            ),
        )
    return LlmTokenUsage(
        status=AvailabilityStatus.UNAVAILABLE,
        reason=(
            "OpenRouter token and cost fields are not present in the saved call artifacts"
            if total_calls
            else "No LLM calls were observed for the selected day"
        ),
    )


def build_roles(calls: list[dict[str, Any]]) -> list[LlmRoleUsage]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in calls:
        grouped[str(row.get("role") or "unknown")].append(row)
    roles: list[LlmRoleUsage] = []
    for item in ROLE_CATALOG:
        rows = grouped.get(str(item["role"]), [])
        ordered = sorted(rows, key=lambda row: as_datetime(row.get("saved_at")) or EARLIEST_UTC)
        successful = success_count(rows)
        observed_model = str(ordered[-1].get("model") or "") if ordered else ""
        state = _role_state(str(item["role"]), len(rows), successful)
        roles.append(
            LlmRoleUsage(
                **item,
                observed_model=observed_model or None,
                call_count=len(rows),
                success_count=successful,
                failure_count=len(rows) - successful,
                latest_call_at=as_datetime(ordered[-1].get("saved_at")) if ordered else None,
                state=state,
            )
        )
    return roles


def build_stages(calls: list[dict[str, Any]]) -> list[LlmStageUsage]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in calls:
        key = str(row.get("stage_component") or row.get("stage_name") or row.get("role") or "unknown")
        groups[key].append(row)
    output = [_stage_item(key, rows) for key, rows in groups.items()]
    output.sort(key=lambda item: (item.stage_index is None, item.stage_index or 99, item.stage_label))
    return output


def _stage_item(key: str, rows: list[dict[str, Any]]) -> LlmStageUsage:
    ordered = sorted(rows, key=lambda row: as_datetime(row.get("saved_at")) or EARLIEST_UTC)
    successful = success_count(rows)
    latest = ordered[-1]
    return LlmStageUsage(
        stage_key=key,
        stage_label=str(latest.get("stage_name") or latest.get("call_kind") or key),
        stage_index=_non_negative_int(latest.get("stage_index")),
        call_count=len(rows),
        success_count=successful,
        failure_count=len(rows) - successful,
        model=str(latest.get("model") or "") or None,
        latest_call_at=as_datetime(latest.get("saved_at")),
    )


def _role_state(role: str, count: int, successful: int) -> str:
    if count and successful == count:
        return "ACTIVE"
    return "DEGRADED" if count else "CONFIGURED"


def is_success(value: Any) -> bool:
    return str(value or "").strip().lower() in SUCCESS_STATES


def as_datetime(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return datetime.fromisoformat(f"{text}+00:00") if parsed.tzinfo is None else parsed


def _non_negative_int(value: Any) -> int | None:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
