from __future__ import annotations

from pathlib import Path


SCHEMA_VERSION = "alpha_research_board.v1"
LIVE_RESEARCH_COST_PCT = 0.28

SOURCE_PATHS = {
    "feature_candidates": Path(
        "evaluation/feature_mart/opening_rank1/candidate_selection.json"
    ),
    "prospective_candidates": Path(
        "evaluation/feature_mart/opening_rank1/prospective/"
        "rank1_candidate_shadow_cumulative.json"
    ),
    "prospective_contract": Path(
        "evaluation/feature_mart/opening_rank1/prospective/"
        "frozen_candidate_contract.json"
    ),
    "fresh_change": Path(
        "evaluation/feature_mart/opening_rank1/fresh_change_activation/"
        "fresh_change_activation_cumulative.json"
    ),
    "opening_cumulative": Path(
        "evaluation/opening_rank1_shadow/opening_rank1_shadow_cumulative.json"
    ),
    "latent_reactivation": Path(
        "evaluation/opening_rank1_shadow/latent_watch/"
        "latent_reactivation_forward.json"
    ),
    "btc_woori_history": Path(
        "evaluation/baseline_btc_woori_tech/historical/"
        "q12_v1_v2_historical_review.json"
    ),
}

TRACKS = [
    {
        "track_id": "OPENING_CONDITIONAL",
        "question": "어떤 장초반 셋업이 상승 지속과 과열 소진을 구분하는가?",
        "owner_if_proven": "Scanner 적합도 또는 Monitor 진입 중 하나",
    },
    {
        "track_id": "SCANNER_REACTIVATION_HORIZON",
        "question": "선정 종목이 새 신호로 재점화되는가, 그렇다면 유효 horizon은 언제인가?",
        "owner_if_proven": "Scanner 재관찰 또는 horizon 정책 중 하나",
    },
    {
        "track_id": "BTC_WOORI",
        "question": "BTC 선행 신호에 우기투 가격·거래량 확인이 붙을 때만 유효한가?",
        "owner_if_proven": "독립 BTC-우기투 baseline",
    },
    {
        "track_id": "LARGE_CAP_TWO_SYMBOL",
        "question": "삼성전자·하이닉스 고정 universe에서 반복 가능한 순수익 edge가 있는가?",
        "owner_if_proven": "독립 삼성전자·하이닉스 baseline",
    },
]

SETTLED_FINDINGS = [
    {
        "finding": "장초반 Rank-1 전부 진입",
        "status": "REJECTED",
        "reason": "종목 집중도 gate를 통과하지 못해 전면 진입은 허용되지 않음.",
    },
    {
        "finding": "진입 guard 전면 완화",
        "status": "REJECTED",
        "reason": "차단 후보 전체가 좋은 기회였다는 근거가 없음.",
    },
    {
        "finding": "손실 후 동일 종목 재진입",
        "status": "RETAIN_BLOCK",
        "reason": "손실 조건의 반복 진입이 성과를 악화함.",
    },
    {
        "finding": "조건 없는 보유 연장",
        "status": "REJECTED",
        "reason": "유리한 horizon은 셋업별로 다르고 EOD에서 수익 반납이 반복됨.",
    },
    {
        "finding": "Strategist 랭킹 overlay",
        "status": "NEUTRAL",
        "reason": "측정된 overlay에서 안정적이고 유의미한 alpha가 확인되지 않음.",
    },
    {
        "finding": "다른 종목 메모리 혼입 영향",
        "status": "EXCLUDE_CONTAMINATED_HISTORY",
        "reason": "재사용 가능한 구분자가 아니라 계측 결함으로 분류함.",
    },
]
