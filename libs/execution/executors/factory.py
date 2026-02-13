from __future__ import annotations

import os
import inspect
from typing import Optional, Any

from libs.execution.executors.mock_executor import MockExecutor
from libs.execution.executors.real_executor import RealExecutor
from libs.core.settings import Settings


def get_executor(settings: Optional[Settings] = None, *, catalog: Any = None, **kwargs: Any):
    """Select executor by EXECUTION_MODE (mock|real). Default: mock.

    Notes
    - We keep **kwargs and optional `catalog` for forward compatibility.
    - Some repos' RealExecutor does not accept `catalog`. We detect support via signature
      and only pass it when available, to avoid runtime TypeError.
    """
    s = settings or Settings.from_env()

    mode = (os.getenv("EXECUTION_MODE", "") or s.kiwoom_mode or "mock").lower()
    if mode == "real":
        init_sig = inspect.signature(RealExecutor.__init__)
        init_kwargs: dict[str, Any] = {"settings": s, "http": kwargs.get("http")}
        if "catalog" in init_sig.parameters:
            init_kwargs["catalog"] = catalog
        return RealExecutor(**init_kwargs)

    # Mock executor doesn't need catalog; it only needs base_url.
    return MockExecutor(base_url=s.base_url)
