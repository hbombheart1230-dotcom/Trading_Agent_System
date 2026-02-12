import pytest

from libs.execution.executors.real_executor import RealExecutor
from libs.execution.executors.base import ExecutionDisabledError
from libs.catalog.api_request_builder import PreparedRequest
from libs.core.settings import Settings


def test_real_executor_disabled_by_default(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EXECUTION_ENABLED", raising=False)
    monkeypatch.setenv("KIWOOM_MODE", "real")
    s = Settings.from_env(env_path="__missing__.env")
    ex = RealExecutor(settings=s)

    req = PreparedRequest(api_id="X", method="POST", path="/orders", headers={}, query={}, body={"b": 2})
    with pytest.raises(ExecutionDisabledError):
        ex.execute(req)
