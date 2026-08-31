from __future__ import annotations

from typing import Optional, Set

from libs.core.symbols import normalize_symbol


def parse_symbol_allowlist(raw: Optional[str]) -> Set[str]:
    """Canonical SYMBOL_ALLOWLIST parser.

    Empty/missing input disables the guard (returns an empty set). Each
    comma-separated entry is normalized via ``libs.core.symbols.normalize_symbol``
    so callers compare against a consistent symbol form regardless of source.

    Single source of truth for parsing logic previously duplicated (and
    drifted) between graphs/nodes/execute_from_packet.py and
    libs/execution/executors/real_executor.py (Phase 1 Execution Safety
    Alignment, Step 3).
    """
    if raw is None:
        return set()
    value = raw.strip()
    if not value:
        return set()
    return {normalize_symbol(x) for x in value.split(",") if normalize_symbol(x)}
