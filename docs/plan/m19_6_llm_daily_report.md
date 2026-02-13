# M19-6: LLM Daily Report Summary

## 목적
- 기존 M13 EOD 리포트(이벤트 카운트 기반)에 **LLM 요약 섹션**을 옵션으로 추가한다.
- 기본값은 OFF. 켜지지 않으면 기존 동작/테스트에 영향이 없어야 한다.

## 동작
- `graphs/pipelines/m13_eod_report.run_m13_eod_report` 실행 후:
  - `state['policy']['use_llm_daily_report']=True` 일 때만 수행
  - 요약 텍스트를 생성하고 `daily_report`에 기록

### 출력
- `state['daily_report']['llm_summary']` 추가
- 생성된 `daily_report_YYYY-MM-DD.md` 끝에 다음 섹션을 append
  - `## LLM Summary`

## 네트워크/안전
- `DRY_RUN=1`이면 네트워크 호출 금지
  - 테스트에서는 `state['mock_llm_daily_summary']`로 우회
- `OPENROUTER_API_KEY` 미설정이면 빈 문자열 반환

## 테스트
- `tests/test_m19_6_llm_daily_report.py`
  - DRY_RUN + mock summary로 파일 append 검증

## 향후 확장
- 리포터 역할 모델 분리: `OPENROUTER_MODEL_REPORTER`
- 입력 컨텍스트 확장: 승인/거절 사유 분포, top symbols, 수익률 등