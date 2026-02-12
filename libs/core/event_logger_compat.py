from __future__ import annotations

from typing import Any


def get_event_logger(name: str):
    """Create EventLogger in a backward-compatible way.

    Some project versions define EventLogger(__init__(node=...)),
    others define EventLogger(name) or EventLogger() with node set later.
    """
    from libs.core.event_logger import EventLogger  # local import to avoid circular deps

    # 1) keyword-style
    try:
        return EventLogger(node=name)  # type: ignore
    except TypeError:
        pass

    # 2) positional name
    try:
        return EventLogger(name)  # type: ignore
    except TypeError:
        pass

    # 3) no-arg + set attribute if possible
    logger = EventLogger()  # type: ignore
    try:
        setattr(logger, "node", name)
    except Exception:
        pass
    return logger
