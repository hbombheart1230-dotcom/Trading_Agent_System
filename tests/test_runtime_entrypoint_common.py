from pathlib import Path

from libs.runtime.entrypoint_common import (
    first_universe_symbol,
    normalize_tick_pipeline,
    resolve_env_path,
    resolve_path_from_root,
)


def test_resolve_env_path_prefers_cli_flag(tmp_path) -> None:
    root = tmp_path
    path = resolve_env_path(root, ["--env-path", "config/.env.live"])
    assert path == root / "config/.env.live"


def test_resolve_env_path_uses_default_root_env() -> None:
    root = Path("C:/repo")
    path = resolve_env_path(root, [])
    assert path == root / ".env"


def test_first_universe_symbol_returns_first_symbol() -> None:
    assert first_universe_symbol({"UNIVERSE_SYMBOLS": "005930, 000660"}) == "005930"


def test_normalize_tick_pipeline_maps_aliases() -> None:
    assert normalize_tick_pipeline("chain") == "integrated_chain"
    assert normalize_tick_pipeline("legacy_m10") == "legacy_m10"


def test_resolve_path_from_root_uses_relative_default() -> None:
    root = Path("C:/repo")
    assert resolve_path_from_root(root, "", "data/state/x.lock") == root / "data/state/x.lock"
