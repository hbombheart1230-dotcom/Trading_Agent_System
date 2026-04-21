# Kiwoom Data Target Map

## 목적

Kiwoom API에서 가져올 수 있는 유효한 정보를 아래 축으로 정리한다.

- scanner
- strategist
- account truth
- order/fill truth
- pnl/fee/tax truth
- sizing truth

중요:
- 이 문서는 가져올 가치가 있는 Kiwoom 데이터 전체를 정리한다.
- runtime 적용 순서와 우선순위는 별도로 둔다.
- Kiwoom 값이 1순위 truth이고, 로컬 계산값은 fallback이다.
- 조건검색은 catalog에는 있지만 모의투자 미지원이라 실전 scanner source에서는 제외한다.

## 1. 가격 / 체결 / 호가 / 분봉

용도:
- scanner
- monitor
- carry review
- report mark/fill 분리

가져올 값:
- 현재가
- 시가 대비 등락률
- 누적 거래량
- 누적 거래대금
- 최우선 매수호가
- 최우선 매도호가
- 호가 잔량
- 분봉 OHLCV
- 예상체결 등락률
- 시가 강도

verified API id:
- `ka10003` 체결정보요청
- `ka10004` 주식호가요청
- `ka10080` minute OHLCV
- `ka10028` 시가대비등락률요청
- `ka10029` 예상체결등락률요청

실시간 websocket:
- `0B` 주식체결
- `0C` 주식우선호가
- `0D` 주식호가잔량

## 2. scanner 후보 풀 / heat / surge

용도:
- candidate pool
- source weighting
- momentum / leadership
- liquidity filter

가져올 값:
- 거래량 상위
- 거래대금 상위
- 등락률 상위
- 거래량 급증
- 급등락
- 상하한가 / 신고저가
- 실시간 종목순위

verified API id:
- `ka10030` 당일거래량상위요청
  - `sort_tp=1` 거래량
  - `sort_tp=3` 거래대금
- `ka10027` 전일대비등락률상위요청
- `ka10023` 거래량급증요청
- `ka10019` 가격급등락요청
- `ka10017` 상하한가요청
- `ka10016` 신고저가요청
- `ka00198` 실시간종목조회순위

조건검색 catalog reference:
- `ka10171` 조건검색 목록조회
- `ka10172` 조건검색 요청 일반
- `ka10173` 조건검색 요청 실시간
- `ka10174` 조건검색 실시간 해제

중요:
- 조건검색은 catalog reference로만 유지한다.
- 모의투자 미지원이라 실전 scanner source에서는 제외한다.

## 3. 테마 / 업종 / breadth / flow

용도:
- strategist advisory
- scanner sector/theme boost
- commander session posture

가져올 값:
- 테마 강도
- 테마 그룹 최근 성과
- 업종 프로그램 수급
- 업종 breadth
- 종목별 프로그램 매매
- 외국인 / 기관 흐름
- 외인 연속 순매수 / 상위

verified API id:
- `ka90001` 테마그룹별요청
- `ka10010` 업종프로그램요청
- `ka10008` 외국인 종목별 매매동향
- `ka10009` 기관 수급
- `ka10034` 외인기관매매상위요청
- `ka10035` 외인연속순매수상위요청
- `ka10036` 외인한도소진율증가상위

실시간 websocket:
- `0U` 업종등락
- `0w` 종목프로그램매매
- `0F` 거래원 흐름

## 4. 신용 / 공매도 / 과열 / 레버리지

용도:
- strategist risk tone
- scanner penalty
- carry review

가져올 값:
- 신용매매 동향
- 공매도 추이
- 신용 가능 종목 / 조건

verified API id:
- `ka10013` 신용매매동향요청
- `ka10014` 공매도추이요청
- `kt20016` 신용융자가능종목요청
- `kt20017` 신용융자가능문의

## 5. account truth

용도:
- commander carry control
- monitor exit cross-check
- strategist carry review
- report truth

가져올 값:
- 보유 종목
- 보유 수량
- 평균단가
- 현재가
- 미실현손익
- 계좌 손익률
- 당일 계좌 현황
- 일별 계좌 수익률
- 실시간 잔고 변경

verified API id:
- `kt00018` 계좌평가잔고내역요청
- `kt00017` 계좌별당일현황요청
- `kt00016` 일별계좌수익률현황요청
- `ka01690` 일별잔고수익률

실시간 websocket:
- `04` 잔고

## 6. order / fill truth

용도:
- 실제 청산 체결가
- 실제 체결 수량
- fill status
- report truth
- reconciliation

가져올 값:
- 주문번호
- 체결 상태
- 체결 수량
- 체결 단가
- 미체결
- 주문/체결 시간

verified API id:
- `kt00007` 계좌별주문체결내역상세요청
- `kt00009` 계좌별주문체결현황요청

실시간 websocket:
- `00` 주문체결

## 7. pnl / fee / tax / day trade truth

용도:
- 앱과 report 손익 정렬
- gross/net pnl 분리
- 당일 실현손익률 truth

가져올 값:
- gross realized pnl
- net realized pnl
- fee
- tax
- day realized pnl ratio
- day trade summary

현재 상태:
- 값은 반드시 필요하다.
- endpoint id와 field contract는 account/order catalog 기준으로 추가 inventory 확인이 필요하다.

인접 verified endpoint:
- `kt00016`
- `kt00017`
- `ka01690`
- `kt00007`
- `kt00009`

## 8. 주문가능금액 / sizing truth

용도:
- buy sizing
- risk control
- re-entry 가능 cash

가져올 값:
- 주문가능금액
- 예수금
- 출금가능
- 증거금 반영 가능 수량

현재 상태:
- 중요도는 높다.
- 정확한 endpoint / field inventory를 추가 확인해야 한다.

## 9. 역할별 실제 우선순위

### scanner
필수:
- `ka10030`
- `ka10027`
- `ka10023`
- `ka10028`
- `ka10029`
- `ka10003`
- `ka10080`

보류:
- 조건검색

있으면 좋은 것:
- `ka00198`
- `ka10016`
- `ka10017`
- `0B`
- `0C`
- `0D`

### strategist
필수:
- `ka90001`
- `ka10010`
- `ka10008`
- `ka10009`
- `kt00018`
- `kt00017`
- `kt00016`
- `ka01690`

있으면 좋은 것:
- `ka10013`
- `ka10014`
- `0U`
- `0w`
- `0F`
- `ka10004`
- `ka10080`

### account / report truth
필수:
- `kt00018`
- `kt00007`
- `kt00009`
- `kt00017`
- `kt00016`
- `ka01690`
- fee/tax source
- 주문가능금액 source

## 10. 구현 packet 제안

1. `broker_account_truth_packet`
- 잔고, 보유, 평균단가, 미실현손익, 주문가능금액

2. `broker_fill_truth_packet`
- 주문번호, 체결수량, 체결단가, 체결상태, 수수료, 세금

3. `broker_day_pnl_truth_packet`
- 당일 실현손익, gross/net pnl, day realized pnl ratio

4. `kiwoom_market_advisory_packet`
- 테마, 업종, breadth, 외인/기관 flow, 신용/공매도
