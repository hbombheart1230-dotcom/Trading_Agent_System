# Default Rule Engine (자동 기본값 주입)

- `scripts/build_default_rules.py`는 `data/specs/kiwoom_api_list_tagged.jsonl`를 읽어
  `data/specs/default_rules.json`을 생성합니다.
- 런타임에서 `libs/skills/rules.py`가 이 파일을 읽어, API별/프리픽스별 기본값을 자동 주입합니다.
- 결과: YAML은 step+map만 남고, 필수/기본 파라미터는 rules로 흡수됩니다.

## 사용
```bash
python scripts/build_default_rules.py
# 또는
python scripts/build_default_rules.py --in data/specs/kiwoom_api_list_tagged.jsonl --out data/specs/default_rules.json
```
