# M15 구조 설명

## 포함 내용 요약

### 신규 Agent Layer 구조
- `libs/agent/commander.py`
- `libs/agent/strategist.py`
- `libs/agent/scanner.py`
- `libs/agent/monitor.py`
- `libs/agent/reporter.py`
- `libs/agent/executor.py` (Agent 레벨 Executor)

### Execution Layer 유지
- `libs/execution/executor.py` (실제 API 실행 전용)

### Supervisor / Approval
- approval_mode 기반 동작 (auto/manual)
- AUTO_APPROVE는 호환 변수로 유지하되, 문서/운영에서는 APPROVAL_MODE를 기본으로 사용
- reject/preview/list/last 유지

### Safety
- `SYMBOL_ALLOWLIST` (env 비어있으면 비활성)
- `EXECUTION_ENABLED` guard
- `KIWOOM_MODE` mock/real 분기

## 참고
- 본 문서는 구조 설명용이며, 세부 동작은 `docs/architecture/*` 참고
