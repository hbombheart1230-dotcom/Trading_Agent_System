# Q9/Q10/Q11/Q12 Five-Day Freeze

Effective: 2026-06-29

## Window

- Target: five valid full regular-session trading days
- Planned weekdays: 2026-06-29, 2026-06-30, 2026-07-01,
  2026-07-02, 2026-07-03
- Holidays or materially incomplete sessions do not count.
- The window ends after five valid days, not after five calendar weekdays.
- 2026-06-24 through 2026-06-26 remain historical context only. They do not
  count toward this renewed five-valid-day window.

## Frozen Behavior

The following behavior must not change during the window:

- Q9 Scanner sourcing, filtering, ranking, and weighting
- Q9 Strategist prompts, schemas, routing, cache, and recommendations
- Q9 Commander approval, veto, routing, and risk controls
- Q9 Monitor entry, exit, and hold rules
- execution and order behavior
- Samsung/Hynix ranking formula
- Samsung/Hynix entry conditions and thresholds
- Samsung/Hynix exit conditions
- Q11 opening opportunity scoring and virtual trade rules
- Q12 BTC/Woori scoring and virtual entry rules

Only observability and reporting defects may be fixed.

## Daily Closeout

Kiwoom regular-session close confirmation invokes the existing
`closeout_maintenance` path. It now also performs:

1. Q9 daily evaluation generation
2. Samsung/Hynix baseline intraday reconstruction and report generation
3. unified Q9 P/A/B/C versus baseline comparison generation
4. Q11 opening opportunity report generation
5. Q12 BTC/Woori report generation
6. forward-window and evidence-status verification
7. Commander Final alpha recording for each horizon

Manual command:

```powershell
venv\Scripts\python.exe scripts\run_frozen_q9_baseline_closeout.py --day YYYY-MM-DD
```

Artifacts:

- `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/daily_ledger.json`
- `reports/evaluation/freeze_window/q9_q10_q11_q12_5d_20260629/daily_ledger.md`
- daily `post_close_verification.json`

## Evidence Verification

For each horizon, comparable evidence requires both:

- Q9 C Commander Final forward observations
- Samsung/Hynix baseline Top-1 forward observations

After all four forward horizons are comparable:

- unified `evidence_status` must be `COMPLETE`
- no horizon may remain `INSUFFICIENT_EVIDENCE`
- Commander alpha is recorded as:

```text
Q9 C average net return - baseline Top-1 average net return
```

If forward windows are complete but evidence remains insufficient, the day is
flagged as a reporting/observability verification error. Performance quality
does not invalidate the day.
