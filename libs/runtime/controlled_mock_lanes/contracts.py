from __future__ import annotations

from typing import Final


SCHEMA_VERSION: Final = "controlled_mock_lanes.v1"
LEDGER_SCHEMA_VERSION: Final = "controlled_mock_lane_submissions.v1"

BTC_WOORI: Final = "BTC_WOORI"
Q10_SEMICONDUCTOR: Final = "Q10_SEMICONDUCTOR"
Q10_INDEX: Final = "Q10_INDEX"
INDEPENDENT_LANES: Final = (BTC_WOORI, Q10_SEMICONDUCTOR, Q10_INDEX)

LANE_WINDOWS_KST: Final = {
    BTC_WOORI: ((9, 3), (9, 30)),
    Q10_SEMICONDUCTOR: ((9, 3), (10, 0)),
    Q10_INDEX: ((9, 3), (10, 0)),
}

Q10_TARGET_SYMBOLS: Final = {
    "samsung": "005930",
    "sk_hynix": "000660",
}

Q10_INDEX_SYMBOLS: Final = {
    ("kospi", 1): {"symbol": "069500", "name": "KODEX 200"},
    ("kospi", -1): {"symbol": "114800", "name": "KODEX Inverse"},
    ("kosdaq", 1): {"symbol": "229200", "name": "KODEX KOSDAQ150"},
    ("kosdaq", -1): {"symbol": "251340", "name": "KODEX KOSDAQ150 Futures Inverse"},
}

Q12_SYMBOL: Final = "041190"
DEFAULT_ORDER_QTY: Final = 1
MAX_SIGNAL_AGE_SEC: Final = 7 * 60

