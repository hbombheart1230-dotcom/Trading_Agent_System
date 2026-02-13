# M19-1 Naver News Provider

## 목표
- 뉴스 수집을 “플러그인(provider)”로 분리한 구조에서, Naver News Search API를 실제 구현체로 연결한다.
- 테스트/DRY_RUN은 항상 외부 호출 없이 동작해야 한다.

## 적용 파일
- `libs/news/providers/naver.py`

## 환경변수
- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`

(옵션) 심볼 대신 회사명으로 검색하고 싶으면 `policy["symbol_query_map"]` 또는 ENV로 JSON 맵을 넣는다.

## 동작 규칙
- `DRY_RUN=1` 또는 `policy["dry_run"]=True` → 외부 호출 금지, `{symbol: []}` 반환
- 자격증명 누락 → 외부 호출 금지, `{symbol: []}` 반환
- 네트워크 오류/비정상 응답 → best-effort로 빈 리스트

## policy 키
- `naver_news_url` (default: Naver 뉴스 검색 URL)
- `naver_news_sort` (default: `date`)
- `news_max_items_per_symbol` (default: 5)
- `news_timeout_sec` (default: 3.0)
- `news_throttle_sec` (default: 0.0)
- `symbol_query_map` (dict[str,str])

