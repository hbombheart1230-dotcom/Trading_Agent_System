from __future__ import annotations

import os
from typing import Optional, Any

from libs.execution.executors.mock_executor import MockExecutor
from libs.execution.executors.real_executor import RealExecutor
from libs.core.settings import Settings


def get_executor(settings: Optional[Settings] = None, *, catalog: Any = None, **kwargs: Any):
    """Select executor by EXECUTION_MODE (mock|real). Default: mock.

    - Accepts extra kwargs for forward compatibility (e.g., catalog).
    - Demo scripts may pass catalog=...; RealExecutor can optionally use it later.
    """
    s = settings or Settings.from_env()

    mode = (os.getenv("EXECUTION_MODE", "") or s.kiwoom_mode or "mock").lower()
    if mode == "real":
        return RealExecutor(settings=s, http=kwargs.get("http"), catalog=catalog)
    return MockExecutor(base_url=s.base_url)
