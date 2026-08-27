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
