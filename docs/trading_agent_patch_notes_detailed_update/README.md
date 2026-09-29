# Patch Notes Update Contract

이 폴더는 Trading Agent System의 공식 변경 이력 원본입니다.

## 필수 규칙

코드, 설정, 운영 정책, 평가 계측, 데이터 계약, 배포 또는 UI를 패치할 때마다 같은 커밋에서 아래 두 파일을 갱신합니다.

- `patch_notes.json`: UI와 API가 읽는 구조화 원본
- `patch_notes.md`: 사람이 읽는 상세 변경 이력

문서만 수정하는 경우에도 시스템의 운영 방식이나 권위 문서가 달라지면 패치 노트를 남깁니다. 오탈자처럼 의미와 동작이 전혀 변하지 않는 수정만 생략할 수 있습니다.

## JSON 규칙

1. 기존 `entries`는 수정하거나 재정렬하지 않습니다.
2. 새 항목은 배열 끝에 추가합니다.
3. `entry_count`는 실제 `entries` 개수와 일치시킵니다.
4. `date`, `version`, `title`, `stage`, `types`, `summary`, `details`, `impact`, `sources`, `status`를 모두 채웁니다.
5. `sources`에는 실제 저장소 상대 경로만 기록합니다.
6. 과거 항목은 `historical`, 현재 운영 상태를 나타내는 항목은 `current`를 사용합니다.

## 완료 점검

- UTF-8 JSON 파싱 성공
- `entry_count == len(entries)`
- JSON과 Markdown에 같은 변경 내용 존재
- 근거 파일 경로 존재
- `/api/v1/patch-notes`가 `AVAILABLE` 반환
- Web production build 및 desktop/mobile smoke test 통과

패치 노트 갱신이 빠진 변경은 완료된 패치로 간주하지 않습니다.

## 정본(Canonical Source)과의 관계

- `docs/daily_patch/`: 각 변경의 상세 기술 근거를 남기는 저장소 감사 이력의 정본입니다.
- `patch_notes.json` / `patch_notes.md` (이 폴더): Patch Notes UI/API(`/api/v1/patch-notes`)가 실제로 읽는
  구조화 원본입니다. `docs/daily_patch/`의 내용을 사람이 읽을 수 있게 요약해 반영하되, 두 파일은 별개
  목적(기술 근거 vs. 사용자 대상 변경 이력)을 가진 별도 파일이며 하나가 다른 하나를 자동으로 대체하지
  않습니다.
- `tests/test_patch_notes_sync.py`가 `patch_notes.json`의 최신 날짜가 `docs/daily_patch/`의 최신 날짜보다
  뒤처지지 않는지 검증합니다. 새 형식 동결(formal freeze)이나 주요 마일스톤을 `docs/daily_patch/`에
  기록했다면, 같은 작업에서 이 폴더의 두 파일도 반드시 갱신하십시오.
