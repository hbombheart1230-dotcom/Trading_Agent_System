from __future__ import annotations

from datetime import UTC, datetime

from ..config import ApiSettings
from ..models.profile import ExposureProfileResponse


def build_exposure_profile(settings: ApiSettings) -> ExposureProfileResponse:
    return ExposureProfileResponse(
        profile=settings.exposure_profile.value,
        public_mode=settings.public_mode,
        checked_at=datetime.now(UTC),
        report_content_access=not settings.public_mode,
        redactions=[
            "account_identifiers",
            "order_and_fill_identifiers",
            "absolute_filesystem_paths",
            "raw_prompts_and_responses",
            "credentials_and_environment_values",
            "process_and_host_identifiers",
        ],
    )
