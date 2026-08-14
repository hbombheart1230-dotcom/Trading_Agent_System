from __future__ import annotations

from pathlib import Path

import pytest

from apps.api.infrastructure.paths import PathAccessError, ReadOnlyPathRegistry


def test_registry_resolves_path_inside_allowlisted_root(tmp_path: Path) -> None:
    root = tmp_path / "reports"
    root.mkdir()
    registry = ReadOnlyPathRegistry({"reports": root})

    assert registry.resolve("reports", "daily/summary.json") == (
        root / "daily" / "summary.json"
    ).resolve()


@pytest.mark.parametrize("path", ["../secret", "daily/../../secret"])
def test_registry_blocks_path_traversal(tmp_path: Path, path: str) -> None:
    root = tmp_path / "reports"
    root.mkdir()
    registry = ReadOnlyPathRegistry({"reports": root})

    with pytest.raises(PathAccessError, match="escapes"):
        registry.resolve("reports", path)


def test_registry_blocks_absolute_path(tmp_path: Path) -> None:
    root = tmp_path / "reports"
    root.mkdir()
    registry = ReadOnlyPathRegistry({"reports": root})

    with pytest.raises(PathAccessError, match="absolute"):
        registry.resolve("reports", tmp_path / "secret")


def test_registry_blocks_symlink_escape(tmp_path: Path) -> None:
    root = tmp_path / "reports"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation is unavailable in this environment")

    registry = ReadOnlyPathRegistry({"reports": root})
    with pytest.raises(PathAccessError, match="escapes"):
        registry.resolve("reports", "linked/secret.json")
