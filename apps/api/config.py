from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


def _default_repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _path_from_env(name: str, fallback: Path) -> Path:
    raw = os.getenv(name, "").strip()
    return Path(raw).expanduser().resolve() if raw else fallback.resolve()


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    value = int(raw) if raw else default
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


class ExposureProfile(StrEnum):
    PRIVATE = "private"
    PUBLIC = "public"


def _exposure_profile() -> ExposureProfile:
    raw = os.getenv("OBSERVABILITY_EXPOSURE_PROFILE", "private").strip().lower()
    try:
        return ExposureProfile(raw)
    except ValueError as exc:
        raise ValueError(
            "OBSERVABILITY_EXPOSURE_PROFILE must be private or public"
        ) from exc


@dataclass(frozen=True, slots=True)
class ApiSettings:
    repository_root: Path
    reports_root: Path
    logs_root: Path
    state_root: Path
    max_report_bytes: int = 5 * 1024 * 1024
    max_tail_scan_bytes: int = 32 * 1024 * 1024
    max_event_rows: int = 500
    cache_ttl_seconds: int = 30
    max_period_days: int = 400
    max_trade_bundles: int = 5000
    exposure_profile: ExposureProfile = ExposureProfile.PRIVATE

    @classmethod
    def from_environment(cls) -> "ApiSettings":
        repository_root = _path_from_env(
            "OBSERVABILITY_REPOSITORY_ROOT",
            _default_repository_root(),
        )
        return cls(
            repository_root=repository_root,
            reports_root=_path_from_env(
                "OBSERVABILITY_REPORTS_ROOT",
                repository_root / "reports",
            ),
            logs_root=_path_from_env(
                "OBSERVABILITY_LOGS_ROOT",
                repository_root / "data" / "logs",
            ),
            state_root=_path_from_env(
                "OBSERVABILITY_STATE_ROOT",
                repository_root / "data" / "state",
            ),
            max_report_bytes=_positive_int(
                "OBSERVABILITY_MAX_REPORT_BYTES",
                5 * 1024 * 1024,
            ),
            max_tail_scan_bytes=_positive_int(
                "OBSERVABILITY_MAX_TAIL_SCAN_BYTES",
                32 * 1024 * 1024,
            ),
            max_event_rows=_positive_int("OBSERVABILITY_MAX_EVENT_ROWS", 500),
            cache_ttl_seconds=_positive_int(
                "OBSERVABILITY_CACHE_TTL_SECONDS",
                30,
            ),
            max_period_days=_positive_int(
                "OBSERVABILITY_MAX_PERIOD_DAYS",
                400,
            ),
            max_trade_bundles=_positive_int(
                "OBSERVABILITY_MAX_TRADE_BUNDLES",
                5000,
            ),
            exposure_profile=_exposure_profile(),
        )

    @property
    def public_mode(self) -> bool:
        return self.exposure_profile == ExposureProfile.PUBLIC

    @property
    def source_roots(self) -> dict[str, Path]:
        return {
            "reports": self.reports_root,
            "logs": self.logs_root,
            "state": self.state_root,
        }
