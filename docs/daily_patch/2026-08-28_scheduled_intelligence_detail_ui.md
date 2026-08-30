# 2026-08-28 Scheduled Intelligence Detail UI

## Change

- Kept the compact Preopen / Closeout status cards.
- Added an expandable detail section with strategy frame, risk, model, memory
  application mode, closeout counts, and individual step status.
- Added the briefing, memory receipt, strategy memory, Strategist, closeout,
  and daily intelligence source paths with copy buttons.
- Included preopen data-quality warnings in the visible issue surface.
- Corrected canonical artifact day partitioning to KST so preopen artifacts
  after midnight UTC no longer land in the prior Korean trading-day folder.

## Safety

- Read-only API projection and UI only.
- No scheduler, runtime, memory, strategy, or execution behavior changed.
- Existing misplaced artifacts are preserved; only future writes use the
  corrected KST partition.
- Artifact paths are displayed and copied as text; files cannot be modified
  from the observability UI.

## Verification

- API and deployment contract tests: `16 passed`.
- Web production build: passed.
- Web unit tests: `14 passed`.
- Canonical KST partition and related tests: `38 passed`.
- Full regression: `2677 passed, 1 skipped`.
