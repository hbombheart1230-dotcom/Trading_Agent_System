# 13. 프로젝트 트리

- 마지막 업데이트: 2026-03-10
- 범위: 핵심 디렉터리와 현재 런타임 책임 분리 요약

## Top-Level

```text
Trading_Agent_System/
  graphs/
    nodes/
    pipelines/
  libs/
  scripts/
  tests/
  docs/
  data/
  config/
```

## 핵심 경로

- `graphs/`: 런타임 오케스트레이션 노드/파이프라인
- `libs/`: 전략, 스캐너, 모니터, 실행, 리포트 등 도메인 로직
- `scripts/`: 운영/점검/리포트 스크립트
- `tests/`: 회귀/마일스톤 테스트

## Strategy Candidate Flow (현재)

- `graphs/nodes/strategist_node.py`
  - `themes`, `candidates`, `strategist_output` 생성
- `graphs/nodes/scanner_node.py`
  - 전략가 후보만 평가, `top_stock`, `scanner_output` 생성
- `graphs/nodes/monitor_node.py`
  - 선택 종목의 진입/청산 intent만 생성
- `graphs/nodes/execute_from_packet.py`
  - 승인/가드/실행 경계 유지

## 관련 환경변수

- `TOP_N_CANDIDATES`
- `SYMBOL_ALLOWLIST`
- `MIN_HOLD_SECONDS`
- `SELL_COOLDOWN` 또는 `SELL_COOLDOWN_SEC`
- `MONITOR_EXIT_CONFIRM_TICKS`
