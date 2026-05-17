from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from libs.runtime.entrypoints.live_session_watch import (  # noqa: E402
    KST,
    ROOT as RUNTIME_ROOT,
    evaluate_watch_health,
    main,
)
from libs.runtime.entrypoints.live_session_watch import _build_markdown, _parse_args, _run_live_summary, _run_once  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
