from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from libs.catalog.api_catalog import ApiCatalog
from libs.core.settings import Settings
from libs.read.kiwoom_broker_truth_common import KiwoomBrokerTruthClient, require_api


SNAPSHOT_ROOT = Path("data/logs/kiwoom_account_snapshots")
_AUTH_FAILURE_TOKENS = (
    "Token이 유효하지 않습니다",
    "token",
    "8005",
    "805004",
    "인증에 실패",
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _compact_ts(dt: datetime) -> str:
    return dt.strftime("%Y%m%d_%H%M%SZ")


def _day8(day: str) -> str:
    return str(day or "").replace("-", "")


def _payload_has_auth_failure(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    text = json.dumps(payload, ensure_ascii=False)
    lower = text.lower()
    return any(token.lower() in lower for token in _AUTH_FAILURE_TOKENS)


def _snapshot_latest_eligible(snapshot: Dict[str, Any]) -> bool:
    calls = snapshot.get("calls") if isinstance(snapshot.get("calls"), list) else []
    if not calls:
        return False
    saw_success = False
    for call in calls:
        if not isinstance(call, dict):
            continue
        payload = call.get("payload")
        if _payload_has_auth_failure(payload):
            return False
        if isinstance(payload, dict) and str(payload.get("return_code")) == "0":
            saw_success = True
    return saw_success


class KiwoomAccountSnapshotCollector:
    """Collect broad Kiwoom account/order/PnL truth into append-only JSON files."""

    def __init__(
        self,
        *,
        settings: Optional[Settings] = None,
        catalog: Optional[ApiCatalog] = None,
        executor: Any = None,
    ) -> None:
        self.client = KiwoomBrokerTruthClient(settings=settings, catalog=catalog, executor=executor)
        self.catalog = self.client.catalog

    @classmethod
    def from_env(cls) -> "KiwoomAccountSnapshotCollector":
        return cls()

    def _call(self, api_id: str, title: str, body: Dict[str, Any]) -> Dict[str, Any]:
        started = _utc_now()
        resolved_api_id = api_id
        try:
            resolved_api_id = require_api(self.catalog, api_id, title)
            payload = self.client.call(resolved_api_id, body)
            status = "ok"
            error = ""
        except Exception as exc:
            payload = {}
            status = "error"
            error = str(exc)
        return {
            "api_id": resolved_api_id,
            "title": title,
            "body": dict(body),
            "status": status,
            "error": error,
            "started_at": started.isoformat(timespec="seconds"),
            "finished_at": _utc_now().isoformat(timespec="seconds"),
            "payload": payload,
        }

    def collect(self, *, day: str, trigger: str = "report_generation") -> Dict[str, Any]:
        day_text = str(day or "").strip()
        ymd = _day8(day_text)
        calls: List[Dict[str, Any]] = [
            self._call("ka10170", "당일매매일지요청", {"base_dt": ymd, "ottks_tp": "1", "ch_crd_tp": "0"}),
            self._call("ka10077", "당일실현손익상세요청", {}),
            self._call("ka10074", "일자별실현손익요청", {"strt_dt": ymd, "end_dt": ymd}),
            self._call("ka10072", "일자별종목별실현손익요청_일자", {"stk_cd": "", "strt_dt": ymd}),
            self._call("ka10073", "일자별종목별실현손익요청_기간", {"stk_cd": "", "strt_dt": ymd, "end_dt": ymd}),
            self._call("ka10085", "계좌수익률요청", {"stex_tp": "0"}),
            self._call("ka10075", "미체결요청", {"all_stk_tp": "0", "trde_tp": "0", "stk_cd": "", "stex_tp": "0"}),
            self._call(
                "ka10076",
                "체결요청",
                {"stk_cd": "", "qry_tp": "0", "sell_tp": "0", "ord_no": "", "stex_tp": "0"},
            ),
            self._call(
                "kt00007",
                "계좌별주문체결내역상세요청",
                {
                    "ord_dt": ymd,
                    "qry_tp": "1",
                    "stk_bond_tp": "1",
                    "sell_tp": "0",
                    "stk_cd": "",
                    "fr_ord_no": "",
                    "dmst_stex_tp": "KRX",
                },
            ),
            self._call(
                "kt00009",
                "계좌별주문체결현황요청",
                {
                    "ord_dt": ymd,
                    "stk_bond_tp": "1",
                    "mrkt_tp": "0",
                    "sell_tp": "0",
                    "qry_tp": "4",
                    "stk_cd": "",
                    "fr_ord_no": "",
                    "dmst_stex_tp": "KRX",
                },
            ),
            self._call("kt00015", "위탁종합거래내역요청", {"strt_dt": ymd, "end_dt": ymd, "tp": "3", "stk_cd": "", "crnc_cd": "KRW", "gds_tp": "1", "frgn_stex_code": "", "dmst_stex_tp": "%"}),
            self._call("kt00018", "계좌평가잔고내역요청", {"qry_tp": "1", "dmst_stex_tp": "KRX"}),
            self._call("kt00004", "계좌평가현황요청", {"qry_tp": "0", "dmst_stex_tp": "KRX"}),
            self._call("kt00005", "체결잔고요청", {"dmst_stex_tp": "KRX"}),
            self._call("kt00017", "계좌별당일현황요청", {}),
            self._call("kt00016", "일별계좌수익률상세현황요청", {"fr_dt": ymd, "to_dt": ymd}),
            self._call("kt00001", "예수금상세현황요청", {"qry_tp": "3"}),
            self._call("kt00002", "일별추정예탁자산현황요청", {"start_dt": ymd, "end_dt": ymd}),
            self._call("kt00003", "추정자산조회요청", {"qry_tp": "0"}),
        ]
        ok_count = sum(1 for call in calls if call.get("status") == "ok")
        return {
            "schema_version": "kiwoom_account_snapshot.v1",
            "day": day_text,
            "trigger": str(trigger or "manual"),
            "generated_at": _utc_now().isoformat(timespec="seconds"),
            "summary": {
                "api_call_count": len(calls),
                "ok_count": ok_count,
                "error_count": len(calls) - ok_count,
            },
            "calls": calls,
        }


def save_kiwoom_account_snapshot(
    *,
    day: str,
    trigger: str = "report_generation",
    root: Path = SNAPSHOT_ROOT,
    collector: Optional[KiwoomAccountSnapshotCollector] = None,
) -> Dict[str, Any]:
    generated_at = _utc_now()
    collector = collector or KiwoomAccountSnapshotCollector.from_env()
    snapshot = collector.collect(day=day, trigger=trigger)
    day_dir = root / str(day)
    day_dir.mkdir(parents=True, exist_ok=True)
    path = day_dir / f"{_compact_ts(generated_at)}_{trigger}.json"
    latest_path = day_dir / "latest.json"
    snapshot["path"] = str(path)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    if _snapshot_latest_eligible(snapshot):
        latest_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        snapshot["latest_update_skipped"] = False
    else:
        snapshot["latest_update_skipped"] = True
        snapshot["latest_skip_reason"] = "snapshot_not_latest_eligible"
    snapshot["latest_path"] = str(latest_path)
    return snapshot
