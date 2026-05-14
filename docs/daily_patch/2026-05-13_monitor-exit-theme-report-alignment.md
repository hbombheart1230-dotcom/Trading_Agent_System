# 2026-05-13 Monitor Exit / Theme Report Alignment

## Context

- `TRD_20260513_005380_01` summary showed `모니터 청산 트리거 미확인`.
- The same trade report also described `005380` as sector/theme aligned even though the final traded candidate had no theme boost.

## Findings

- `005380` is Hyundai Mobis, not Hyundai Motor.
- Actual SELL evidence for run `704fd3f83be143d3a4c8efbe7a809b3f` recorded `exit_reason=max_hold` and `active_exit_axis=Max Hold`.
- The canonical monitor artifact had captured the earlier same-run `hold` snapshot and did not overwrite with the later SELL-confirmed snapshot.
- The scanner top pick had theme alignment, but the final traded fallback candidate `005380` had `theme_boost=0.000` and no `sector_theme` source.

## Patch

- Monitor canonical artifacts now overwrite within the same run so the latest monitor decision is preserved.
- Report regeneration reconciles the latest exit monitor timeline before rebuilding deterministic reports.
- Scanner/report enrichment now reanchors the final traded symbol to scanner evidence before deriving selection basis and theme alignment.
- Theme alignment now requires candidate-level `sector_theme` source or positive `theme_boost`; strategist theme presence alone is not enough.

## Verification

- Regenerated `reports/trades/2026-05-13/1400/TRD_20260513_005380_01`.
- Summary now shows `청산 트리거: Max Hold`.
- Selection basis now shows `회전율/거래량, 감성 지원`.
- Detailed report now shows `테마 가점 +0.000`, `테마 정렬 일치 여부 False`.
- Tests: `tests/test_trade_story_pipeline_enrichment.py` and `tests/test_canonical_artifact_validation.py` passed.
