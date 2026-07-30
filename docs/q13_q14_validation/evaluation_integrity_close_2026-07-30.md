# Evaluation Integrity Close - 2026-07-30

## Scope

This close-out fixes evaluation observability and artifact integrity only. It
does not change Scanner, Strategist, Commander, Monitor, order, entry, or exit
behavior.

## Defects Closed

| Defect | Resolution |
| --- | --- |
| Pytest wrote events into `data/logs/events.jsonl` | Canonical event paths are redirected to a process-specific temporary root under pytest. |
| Pytest wrote Q9 windows into production reports | The canonical reports root is redirected under pytest. |
| Pytest wrote quant shadow candidates into production logs | The canonical quant shadow root is redirected under pytest. |
| Fake symbols and fixture identities entered Q9 evidence | Evaluation inventory rejects synthetic identities and non-KRX six-digit symbols. |
| Post-close Scanner-only rows lowered Q9 linkage coverage | Formal Q9 validity uses regular-session windows from 09:00 through 15:30 KST. Post-session rows remain counted separately. |
| No-trade reports treated every approved Monitor NOOP as over-filtering | The report now requires positive net shadow evidence for `POSSIBLE_OVER_FILTERING`; otherwise it emits `FILTERING_REVIEW_REQUIRED`. |
| Zero realized samples could display trading health `GREEN` | Zero samples now produce `UNKNOWN`. |
| Point-in-time positive cost edge was described as statistical plausibility | The diagnosis separates `entry_cost_edge_positive` from statistical evidence and reports insufficient evidence explicitly. |
| Q9 forward recovery used a Samsung/Hynix baseline run ID | Data-provider callers now provide source-specific run ID prefixes. |

## Cleanup Result

The original contaminated material was preserved under:

`data/logs/dev/testing/quarantine/20260730T092633Z`

Removed from canonical evidence:

| Artifact | Removed |
| --- | ---: |
| Synthetic Q9 decision windows | 311 |
| Synthetic quant shadow JSON files | 542 |
| Test event rows | 12,493 |
| Obsolete pytest event log | 2,455,323,300 bytes |

Affected Q8/Q9 dates, the 2026-07-30 operator summary, the June-July cumulative
review, and all available quant trade diagnoses were regenerated from retained
canonical evidence.

## Verified 2026-07-30 State

| Check | Result |
| --- | --- |
| Q9 day validity | `VALID` |
| Formal Scanner windows | 596 |
| Linked windows | 596 |
| Linkage coverage | 100% |
| Post-session windows, excluded from formal validity | 74 |
| Synthetic windows | 0 |
| Forward usable coverage | 99.35% |
| Trading health with zero realized samples | `UNKNOWN` |
| Quant diagnosis parse errors | 0 |

## Frozen Interpretation

- Q13/Q14 attribution formulas remain unchanged.
- Q15-Q17 behavior conclusions must be judged only from clean, regular-session
  evidence.
- A no-trade day is not automatically over-filtering.
- Positive point-in-time cost edge is not statistical proof of a profitable
  thesis.
- Post-session observations may support diagnostics, but they cannot make a
  formal validation day invalid.

## Regression Contract

Tests must use explicit temporary paths or the canonical-path isolation helper.
Any future artifact writer that defaults to a production path must adopt the
same isolation contract before being used in tests.
