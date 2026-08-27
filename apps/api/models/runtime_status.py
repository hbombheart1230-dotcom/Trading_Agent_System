from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .common import AvailabilityStatus


class RuntimeState(StrEnum):
    RUNNING = "RUNNING"
    DELAYED = "DELAYED"
    STALE = "STALE"
    DUPLICATE = "DUPLICATE"
    INCONSISTENT = "INCONSISTENT"
    STOPPED_EXPECTED = "STOPPED_EXPECTED"
    STOPPED_UNEXPECTED = "STOPPED_UNEXPECTED"
    UNKNOWN = "UNKNOWN"


class RuntimeLockStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exists: bool
    owner_pid: int | None
    started_at: datetime | None
    heartbeat_at: datetime | None
    heartbeat_age_seconds: int | None


class RuntimeProcessLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pid: int
    parent_pid: int
    is_owner: bool


class RuntimeProcessStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime | None
    observation_age_seconds: int | None
    raw_process_count: int | None
    logical_session_count: int | None
    tree_state: str
    processes: list[RuntimeProcessLink]


class RuntimeWatchdogStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime | None
    observation_age_seconds: int | None
    fresh: bool
    ok: bool | None
    blockers: list[str]


class RuntimeSupervisorStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    available: bool
    policy_version: str
    decision: str
    decision_reason: str | None
    heartbeat_stale_seconds: int | None
    restart_cooldown_seconds: int | None
    restart_count: int
    max_daily_restarts: int | None
    last_action: str
    last_reason: str | None
    last_restart_at: datetime | None
    last_restart_reason: str | None
    last_restart_success: bool | None
    cooldown_until: datetime | None
    runtime_issue_after: str | None


class RuntimeMarketStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observed_at: datetime | None
    code: str | None
    label: str | None
    expected_running: bool
    expectation_source: str


class RuntimeStatusResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    runtime_state: RuntimeState
    checked_at: datetime
    read_only: bool = True
    execution_callable: bool = False
    lock: RuntimeLockStatus
    process: RuntimeProcessStatus
    watchdog: RuntimeWatchdogStatus
    supervisor: RuntimeSupervisorStatus
    market: RuntimeMarketStatus
    issues: list[str]


class WatchdogHistoryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: str
    observed_at: datetime | None
    ok: bool
    offhours_noop: bool
    action: str
    reason: str | None
    restart_count: int
    max_daily_restarts: int | None
    runtime_before: str
    runtime_after: str
    heartbeat_age_before_seconds: int | None
    heartbeat_age_after_seconds: int | None
    blockers: list[str]


class WatchdogHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    generated_at: datetime
    read_only: bool = True
    execution_callable: bool = False
    items: list[WatchdogHistoryItem]
    issues: list[str]


class ScheduledJobStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: str
    expected_time_kst: str
    day: str | None
    generated_at: datetime | None
    status: str
    memory_status: str | None
    memory_source_day: str | None
    summary: str | None
    issues: list[str]


class ScheduledIntelligenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    generated_at: datetime
    read_only: bool = True
    execution_callable: bool = False
    jobs: list[ScheduledJobStatus]
    issues: list[str]
