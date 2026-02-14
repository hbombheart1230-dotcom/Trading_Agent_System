## M7 – Risk Guardrails & Order Dry-run

- **Supervisor (M7-1)**: env 기반 하드 리스크 가드레일 집행 (AI가 임의 변경 불가)
- **OrderClient (M7-2)**: 주문 요청을 **dry-run 형태로만** 준비 (네트워크 호출 없음)
- **Demo (M7-3)**: discovery→planner→prepare→supervisor→dry-run 파이프라인 확인
  - `python scripts/demo_m7_dry_run_pipeline.py`
