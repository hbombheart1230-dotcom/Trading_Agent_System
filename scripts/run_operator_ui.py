from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run read-only operator monitoring UI.")
    p.add_argument("--env-path", default=".env")
    p.add_argument("--host", default=os.getenv("OPERATOR_UI_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.getenv("OPERATOR_UI_PORT", "8010")))
    p.add_argument("--reload", action="store_true")
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    from apps.operator_ui.main import create_app

    args = _parse_args(argv)
    env_path = Path(str(args.env_path).strip())
    if env_path.exists():
        load_dotenv(env_path, override=False)
    app_target = "apps.operator_ui.main:create_app" if bool(args.reload) else create_app()
    uvicorn.run(
        app_target,
        host=str(args.host),
        port=int(args.port),
        reload=bool(args.reload),
        factory=bool(args.reload),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
