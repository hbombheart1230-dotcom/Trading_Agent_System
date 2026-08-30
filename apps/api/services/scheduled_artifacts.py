from __future__ import annotations

from datetime import UTC, datetime

from ..config import ApiSettings
from ..infrastructure.bounded_reader import BoundedReadError, read_bytes_bounded, read_json_bounded
from ..infrastructure.paths import ReadOnlyPathRegistry
from ..models.runtime_status import ScheduledArtifactContentResponse
from .runtime_status import build_scheduled_intelligence


def build_scheduled_artifact_content(
    settings: ApiSettings,
    requested_path: str,
) -> ScheduledArtifactContentResponse | None:
    normalized = requested_path.strip().replace("\\", "/")
    if not normalized.startswith("reports/"):
        return None

    artifact_labels = {
        artifact.path.replace("\\", "/"): artifact.label
        for job in build_scheduled_intelligence(settings).jobs
        for artifact in job.artifacts
    }
    label = artifact_labels.get(normalized)
    if label is None:
        return None

    relative_path = normalized.removeprefix("reports/")
    path = ReadOnlyPathRegistry({"reports": settings.reports_root}).resolve(
        "reports",
        relative_path,
    )
    if not path.is_file():
        return None

    suffix = path.suffix.lower()
    if suffix == ".json":
        artifact_format = "json"
        json_content = read_json_bounded(path, max_bytes=settings.max_report_bytes)
        text_content = None
    elif suffix in {".md", ".markdown"}:
        artifact_format = "markdown"
        json_content = None
        try:
            text_content = read_bytes_bounded(
                path,
                max_bytes=settings.max_report_bytes,
            ).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BoundedReadError("artifact is not valid UTF-8") from exc
    else:
        return None

    return ScheduledArtifactContentResponse(
        label=label,
        path=normalized,
        size_bytes=path.stat().st_size,
        format=artifact_format,
        json_content=json_content,
        text_content=text_content,
        generated_at=datetime.now(UTC),
    )
