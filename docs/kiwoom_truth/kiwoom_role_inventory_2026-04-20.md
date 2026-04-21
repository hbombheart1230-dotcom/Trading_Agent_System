# Kiwoom Role Inventory

## 목적

Kiwoom API에서 가져올 수 있는 정보를 아래 4개 역할로 다시 정리한다.

1. 스캐너
2. 전략가
3. 계좌 truth
4. 수익/정산 truth

원칙:
- Kiwoom API 값이 1순위 truth다.
- 로컬 계산값과 monitor 관측값은 fallback이다.
- 스캐너와 전략가는 advisory와 ranking에 쓰고,
- 계좌/수익 수치는 truth source로 쓴다.

## 1. 스캐너가 가져올 것

### 핵심 후보 풀 / heat

- `ka10030`
  - 당일 거래량 / 거래대금 상위
  - 후보 풀의 기본 유동성 source
- `ka10027`
  - 전일 대비 등락률 상위
  - 강한 momentum 후보 풀
- `ka10023`
  - 거래량 급증
  - 초반 확산 / 돌파 후보 보강
- `ka10019`
  - 가격 급등락
  - 과열 / 급변 분리
- `ka10017`
  - 상하한가
- `ka10016`
  - 신고저가
- `ka00198`
  - 실시간 종목 조회 순위
  - intraday heat map 보강
- `ka10171` ~ `ka10174`
  - 조건검색 catalog
  - 모의투자 미지원이라 실전 scanner source에서는 제외

### 가격 / 체결 / 분봉

- `ka10003`
  - 현재가, 체결, 누적 거래량/거래대금
- `ka10004`
  - 호가, best bid/ask, 잔량
- `ka10080`
  - 분봉 OHLCV
- `ka10028`
  - 시가 대비 등락률
- `ka10029`
  - 예상체결 등락률
- websocket
  - `0B` 주식체결
  - `0C` 주식우선호가
  - `0D` 주식호가잔량

### 스캐너에서 실제로 쓸 값

- 거래량
- 거래대금
- 시가 대비 등락률
- 예상체결 강도
- 분봉 추세 / 시가 회복 / opening drive
- 호가 spread / 체결 강도 / 잔량 균형

## 2. 전략가가 가져올 것

전략가는 micro tick raw feed보다 regime / breadth / flow / carry review에 필요한 값을 가져오는 게 맞다.

### 테마 / 업종 / breadth

- `ka90001`
  - 테마 그룹
  - 오늘 강한 테마 / 약한 테마
- `ka10010`
  - 업종 프로그램
  - 업종 단위 risk-on / risk-off
- websocket `0U`
  - 업종 등락
  - breadth / leadership

### 수급 / 흐름

- `ka10008`
  - 외국인 수급
- `ka10009`
  - 기관 수급
- `ka10034`
  - 외인/기관 매매 상위
- `ka10035`
  - 외인 연속 순매수 상위
- `ka10036`
  - 외인 한도 소진율 증가 상위
- websocket
  - `0w` 종목 프로그램 매매
  - `0F` 거래원 흐름

### 레버리지 / 과열 / 공매도

- `ka10013`
  - 신용매매 동향
- `ka10014`
  - 공매도 추이
- `kt20016`
  - 신용 융자 가능 종목
- `kt20017`
  - 신용 융자 가능 문의

### carry / selected-symbol review

- `kt00018`
  - 보유 수량, 평균단가, 현재가, 미실현손익
- `ka01690`
  - 일별 잔고 수익률
- `ka10004`
  - selected symbol 호가 quality
- `ka10080`
  - 장초반 회복 / VWAP reclaim / 분봉 상태

### 전략가에서 실제로 만들 packet

- `kiwoom_market_advisory_packet`
  - 테마, 업종, breadth, 수급, 신용/공매도
- `selected_symbol_market_packet`
  - selected symbol 분봉/호가/flow
- `carry_account_packet`
  - 보유 종목 carry review용 계좌 상태

## 3. 계좌 truth로 가져올 것

이 축은 advisory가 아니라 truth다.

### 보유 / 평가 / 잔고

- `kt00018`
  - 보유 종목
  - 보유 수량
  - 평균단가
  - 현재가
  - 미실현손익
  - 계좌 손익률
- `kt00017`
  - 계좌별 당일 현황
- `kt00016`
  - 일별 계좌 수익률 현황
- `ka01690`
  - 일별 잔고 수익률
- websocket `04`
  - 잔고 실시간 변경

### 주문 가능 금액 / sizing truth

- 주문가능금액 관련 Kiwoom account endpoint
- 예수금 / 출금가능 / 주문가능 / 증거금 반영 값
- 신규 진입 / 추가 진입 / 재진입 sizing truth

현재 원칙:
- sizing은 로컬 cash 추정보다 Kiwoom 주문가능금액을 우선한다.

## 4. 수익 / 정산 truth로 가져올 것

### 주문 / 체결 truth

- `kt00007`
  - 계좌별 주문체결내역
- `kt00009`
  - 계좌별 주문체결현황
- websocket `00`
  - 주문체결 실시간

가져와야 할 값:
- 주문번호
- 체결 상태
- 체결 수량
- 체결 단가
- 미체결
- 체결 시간

### 실현 손익 / 당일 매매 / 수수료 / 세금

- 당일 실현손익
- 당일 매매 수익률
- gross pnl
- net pnl
- 수수료
- 세금
- 일별 정산 요약

원칙:
- report의 청산가와 손익률은 broker fill truth가 먼저다.
- monitor current price는 broker fill이 없을 때만 fallback이다.
- fee/tax를 분리해서 gross와 net을 같이 남겨야 한다.

## 5. 역할별 우선순위

### 1순위

- 계좌 truth
- 주문 / 체결 truth
- 수수료 / 세금 / 당일 실현손익 truth

이유:
- 앱과 report 정합성 문제를 바로 잡는 핵심이다.

### 2순위

- 전략가 Kiwoom advisory packet

이유:
- regime / sector / flow / carry review 품질을 올릴 수 있다.

### 3순위

- 스캐너 source 확장

이유:
- 이미 기본 source는 있고, 확장은 그 다음이다.

## 6. 구현 순서

1. `broker_account_truth_packet`
2. `broker_fill_truth_packet`
3. `broker_day_pnl_truth_packet`
4. `kiwoom_market_advisory_packet`
5. scanner source 확장
