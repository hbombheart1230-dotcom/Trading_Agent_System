# Daily Patch Log - 일일 패치 노트

## Folder Title Recommendation

Recommended title: `Daily Patch Log - 일일 패치 노트`

This folder is the operator-facing daily record for runtime, strategy, reporting, and safety patches.

## Naming Rule

Use one file per trading day:

```text
YYYY-MM-DD_short-main-title.md
```

Examples:

- `2026-04-29_strategy-conservatism-runtime-guards.md`
- `2026-04-30_entry-gate-reporting-memory-defaults.md`
- `2026-05-04_intraday-cash-truth-ai-report-check.md`

## What To Record

- reason for the patch
- changed runtime behavior
- changed report/operator visibility
- validation commands and results
- restart status, when the live process was restarted
- remaining follow-up items

Keep this folder concise. Detailed design notes can stay in each owner folder, and this folder should link or summarize the daily operational change.

## Latest Weekend Review

- `2026-05-09_weekend-validation-report-regeneration-review.md`: 2026-04-29 through 2026-05-08 patch status review, report regeneration timeout fix, and next live-check list.
