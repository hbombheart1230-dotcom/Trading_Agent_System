from __future__ import annotations

from pathlib import Path, PurePath


class PathAccessError(ValueError):
    pass


class ReadOnlyPathRegistry:
    def __init__(self, roots: dict[str, Path]) -> None:
        self._roots = {name: path.resolve() for name, path in roots.items()}

    @property
    def source_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._roots))

    def resolve(self, source: str, relative_path: str | PurePath) -> Path:
        root = self._roots.get(source)
        if root is None:
            raise PathAccessError(f"unknown source: {source}")

        relative = Path(relative_path)
        if relative.is_absolute():
            raise PathAccessError("absolute paths are not allowed")

        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise PathAccessError("path escapes configured source root") from exc
        return candidate
