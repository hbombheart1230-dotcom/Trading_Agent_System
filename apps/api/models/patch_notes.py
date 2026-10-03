from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .common import AvailabilityStatus


class PatchNoteProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    development_era: str | None = None
    owner: str | None = None
    reviewer: str | None = None
    final_approval: str | None = None
    verification: str | None = None
    source_baseline: str | None = None
    provenance_baseline: str | None = None


class PatchNoteEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str
    version: str
    title: str
    stage: str
    types: list[str]
    summary: str
    details: list[str]
    impact: str
    sources: list[str]
    status: str
    provenance: PatchNoteProvenance | None = None


class PatchNotesResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    schema_version: str
    generated_for: str
    entry_count: int = Field(ge=0)
    stages: list[str]
    types: list[str]
    entries: list[PatchNoteEntry]
    reason: str | None = None
    read_only: bool = True
    execution_callable: bool = False
