# graphs/nodes/ensure_token.py

from libs.event_logger import EventLogger
from pathlib import Path

# ⬇️ (이미 있다면 중복 추가 X)
LOGGER = EventLogger(
    log_path=Path("data/logs/events.jsonl")
)

def ensure_token(state: dict) -> dict:
    run_id = state["run_id"]

    # ⬇️ START 로그 (추가)
    LOGGER.log(
        run_id=run_id,
        stage="ensure_token",
        event="start",
        payload={}
    )

    # --- 기존 토큰 확인 로직 ---
    # 예:
    # if not token_valid():
    #     refresh_token()
    # state["token"] = token
    # ---------------------------

    # ⬇️ END 로그 (추가)
    LOGGER.log(
        run_id=run_id,
        stage="ensure_token",
        event="end",
        payload={"status": "ok"}
    )

    return state
