# M13 Runtime Loop (Test-first)

## Goal
- 운영 루프를 **테스트로 먼저 고정**하고, 동일한 코드를 CLI에서 실행.
- 장중 Tick(M10) + 장마감 EOD 리포트(M11) + 상태 저장(M10) 연결.

## Components
- **m13_tick**: 장중일 때만 M10 실행
- **m13_eod_report**: 장마감 후 1회 리포트 생성
- **m13_live_loop**: load → tick → eod → save (one iteration)

## Why test-first?
- 장 시간/스케줄/상태 꼬임 방지
- CLI는 thin wrapper

## Next
- CLI 옵션 확장 (--dry-run, --until)
- 장외/휴장 캘린더 연동
