# M11-2 Scanner (후보 종목 스캔)

- 날짜: 2026-02-11
- 목적: 단일 종목 의사결정(M11-1)을 **다종목 후보 → 1종목 선택** 구조로 확장한다.
- 원칙: M10 실행 계층은 그대로 유지하고, M11에서 `symbol`을 결정해 흘려보낸다.

## 산출물
- `graphs/nodes/scan_candidates.py`
  - `state['candidates']` 생성
  - 우선순위: `state['universe']` > env `UNIVERSE_SYMBOLS` > 기본 ["005930","000660"]

- `graphs/nodes/select_candidate.py`
  - `state['selected_symbol']` / `state['symbol']` 설정
  - 기본: 첫 후보 선택
  - 옵션: `state['candidate_prices']`가 있으면 최저가 우선(placeholder)

- `graphs/pipelines/m11_2_live_pipeline.py`
  - scan → select → snapshot(M9) → risk(M10) → decide(M11) → execute(M10) → persist(M10)

## 다음 확장 (M11-3)
- 후보별 가격 조회(배치) 후 ranking/score 기반 선택
- 조건검색/거래대금/변동성 등 스캐너 피처 추가
