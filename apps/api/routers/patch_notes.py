from __future__ import annotations

from fastapi import APIRouter, Request

from ..models.patch_notes import PatchNotesResponse
from ..services.patch_notes import build_patch_notes


router = APIRouter(prefix="/api/v1/patch-notes", tags=["patch-notes"])


@router.get("", response_model=PatchNotesResponse)
def patch_notes(request: Request) -> PatchNotesResponse:
    return build_patch_notes(request.app.state.settings)
