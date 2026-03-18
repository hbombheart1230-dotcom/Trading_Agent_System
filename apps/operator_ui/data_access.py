from __future__ import annotations

# Thin compatibility facade:
# - Keep existing import path `apps.operator_ui.data_access`
# - Delegate implementation to focused modules / core readers

from apps.operator_ui import data_access_core as _core

globals().update({name: value for name, value in vars(_core).items() if not name.startswith("__")})
__all__ = [name for name in vars(_core).keys() if not name.startswith("__")]
