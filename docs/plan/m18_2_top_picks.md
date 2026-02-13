# M18-2 Top Picks: 랭킹 + 조건검색식 교집합

## 목표
- 전일 거래대금/거래량/등락률 등 랭킹으로 후보 풀을 만든 뒤,
- **조건검색식 결과**로 필터링하여 Top Picks 후보를 생성한다.

## 규칙
- `mock_rank_symbols`(또는 랭킹 결과)의 **순서를 유지**한다.
- `mock_condition_symbols`(또는 조건검색식 결과)가 비어있지 않으면:
  - 최종 후보 = rank 리스트 ∩ condition 리스트 (rank 순서 유지)
- condition이 비어있으면:
  - 최종 후보 = rank 리스트 상위 topk

## 정책 키
- `candidate_rank_mode`: value/volume/change
- `candidate_rank_topn`: rank 후보 풀 크기
- `candidate_topk`: 최종 후보 개수
- `candidate_source`: top_picks

## 테스트 포인트
- 교집합 결과가 rank 순서를 유지하는지
- condition이 비면 rank만으로 topk가 선택되는지
