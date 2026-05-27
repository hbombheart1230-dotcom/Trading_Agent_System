# 2026-05-24 Kiwoom Account Snapshot Archive

## 목적

리포트 개수와 Kiwoom 주문/체결 수를 대조하는 시점마다, 현재 시스템이 바로 쓰지 않는 Kiwoom 계좌/손익/주문 원천 데이터도 날짜별 JSON으로 보관한다.

## 저장 위치

- 루트: `data/logs/kiwoom_account_snapshots`
- 날짜별 폴더: `data/logs/kiwoom_account_snapshots/YYYY-MM-DD/`
- 개별 스냅샷: `YYYYMMDD_HHMMSSZ_report_generation.json`
- 최신 스냅샷 별칭: `latest.json`

## 수집 API

- 손익/당일매매: `ka10170`, `ka10077`, `ka10074`, `ka10072`, `ka10073`, `ka10085`
- 주문/체결/미체결: `ka10075`, `ka10076`, `kt00007`, `kt00009`
- 거래내역/잔고/계좌: `kt00015`, `kt00018`, `kt00004`, `kt00005`, `kt00017`, `kt00016`, `kt00001`, `kt00002`, `kt00003`

## 운영 방식

- `Broker Alignment` 생성 시점에 같이 실행한다.
- API별 실패는 해당 call의 `status=error`로 저장하고, 전체 리포트 생성을 막지 않는다.
- `daily_report`와 `ai_trade_summary`에는 snapshot 경로와 호출 성공/실패 요약만 표기한다.
