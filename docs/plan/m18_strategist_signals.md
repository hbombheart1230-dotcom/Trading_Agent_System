# Strategist 입력 신호 설계 (M18+)

전략가(Strategist)는 **수동 종목 선택 없이** 시장 데이터를 기반으로 3~5개 후보를 자동 생성하고,  
하위 노드(Scanner/Monitor/Supervisor)가 동일한 기준으로 판단할 수 있도록 **정책(Policy) + 신호(Signal)**를 함께 제공한다.

## 1) Strategist가 가져올 입력 신호(초안)

### 1. Global Sentiment
- **Source**: yfinance (또는 동등 데이터 소스)
- **목적**: 오늘의 시장 분위기(리스크 온/오프) 판단
- **지표 예시**
  - S&P500 / NASDAQ 종가 변화율
  - USD/KRW 환율 변화(원화 강/약)
  - 미 국채금리(예: 10Y) 변화
- **출력**
  - `state["macro"]["sentiment"] = {"risk_on": bool, "score": float, "features": {...}}`
  - `policy`에 영향을 줄 수 있음(예: risk_on이면 `max_risk` 완화)

### 2. Top Picks (시장 스캔 후보)
- **Source**: PyKRX / Kiwoom API
- **목적**: 전일/당일 **거래대금 상위 + 조건검색식 결과**를 조합해 후보 풀 생성
- **추천 1차 구성**
  - 거래대금 상위 Top-N에서
  - 조건검색식(있다면)으로 필터링
  - 최종 3~5개 후보로 축약
- **출력**
  - `state["candidates"] = [{"symbol": "...", "why": "..."} ...]`

### 3. News Analysis (호재/악재 점수화)
- **Source**: Naver API / Google News
- **목적**: 후보 종목 뉴스 기반으로 **Sentiment Score** 부여
- **흐름**
  1) 후보(3~5개)별 뉴스 수집
  2) LLM에 요약 + 호재/악재 점수화 요청
  3) `Scanner` 점수(score) 또는 `risk/confidence`에 반영
- **출력**
  - `state["news"] = {"<symbol>": {"score": float, "summary": str, "items": [...]}}`

## 2) 노드 책임 분리 원칙(확정)

- Strategist: **후보 생성 + 정책 결정(임계값/리트라이)**, 거시/뉴스 신호를 “준비”
- Scanner: 후보별 데이터/피처 계산 + 랭킹 + selected 1개
- Monitor: selected 1개에 대해 **OrderIntent만 생성**
- Supervisor: 승인/리스크 검증/가드
- Executor: 승인된 intent 실행

## 3) 단계적 적용(테스트 우선)

1) M18-1: Kiwoom 랭킹 기반 후보 생성 (네트워크 실패 시 DRY_RUN fallback)
2) M18-2: **Top Picks** = (거래대금/거래량 등 랭킹 Top-N) + (조건검색식 결과로 필터링)
3) M18-3: 뉴스 수집/LLM 점수화 연결(옵션)

## 4) Policy 키 (초기 고정)

Strategist 노드는 아래 정책 키를 읽는다.

- `candidate_source`: `top_picks` | `market_rank`
- `candidate_rank_mode`: `value` | `volume` | `change_rate`
- `candidate_topk`: 최종 후보 수 (기본 5)
- `candidate_rank_topn`: 랭킹에서 몇 개를 먼저 뽑아 필터할지 (기본 30)
- `condition_id`: (선택) 조건검색식 id
- `condition_name`: (선택) 조건검색식 이름

테스트/DRY_RUN에서 주입 가능한 값:

- `state['candidate_symbols']`: 후보 강제 주입 (최우선)
- `state['mock_rank_symbols']`: 랭킹 리스트 강제 주입
- `state['mock_condition_symbols']`: 조건검색 결과 강제 주입

각 단계는 **pytest로 고정**하고 다음 단계로 확장한다.
