# Research Portfolio Freeze — 2026-09-16

This document is the single authority for: *what research keeps running, what waits, what is
under termination review, and what is blocked by data/contract problems*, as of the
2026-09-16 cutoff. It is a **research governance** document — not a code authority, not a
UEF authority, not a runtime authority.

Primary source: [`tmp/research_review_2026-09-16.md`](../../tmp/research_review_2026-09-16.md)
(full per-program findings, citations, and the raw 29-family review this freeze narrows).
Any number in this document that conflicts with that source has been deliberately corrected
per §17 below; every other figure is carried over unchanged.

```
RESEARCH PORTFOLIO FREEZE — 2026-09-16

EDGE_CONFIRMED:              0
ACTIVE KEEP:                 5
WATCH:                       3
RETAINED NON-ALPHA CONTROLS: 3   (Q11, Q15, Q10 Semiconductor)
DEPRECATE_REVIEW:            5
BLOCKED:                     7
```

---

## 1. Governance Principle

```
PIPELINE WORKS ≠ CANONICALIZATION PASS ≠ DISCRIMINATOR FOUND ≠ EDGE FOUND ≠ LIVE PROMOTION
```

As of this freeze: **`EDGE_CONFIRMED = 0`** across the entire research portfolio. No research
result currently in evidence grants authority to change live strategy logic, thresholds, or
policy. UEF adapter status (FROZEN / BLOCKED / PROVISIONALLY CLOSED) is an infrastructure
verdict about lossless canonicalization, never an alpha verdict, and is not treated as one
anywhere in this document.

---

## 2. Status Vocabulary

- **KEEP** — active research; forward evidence collection continues.
- **WATCH** — hypothesis still alive, not actively expanded; re-evaluated once a specific
  measurement/data condition is met.
- **DEPRECATE_REVIEW** — no longer actively maintained as an independent alpha research
  track. Does **not** mean code deletion — a baseline/control/diagnostic role may remain.
- **BLOCKED** — no further alpha/causal conclusion is drawn until a named data/schema/
  provenance/control-design problem is resolved.

---

## 3. Active Research Portfolio — Exactly 5 (KEEP)

### KEEP-1 — Short Alpha Discriminator

Canonical name: `HIGH_COMMON_SHORT_ALPHA_V1` / Short Alpha Discriminator.

```
N = 39
+30m avg ≈ +0.81%          (control TOP_VALUE_VOLUME ≈ +0.06%)
PF ≈ 1.38, cost-aware

EOD avg ≈ -0.81%
market snapshot coverage ≈ 58.6%   (promotion threshold = 80%)

EDGE:            EDGE_PROMISING
DISCRIMINATOR:   FOUND
LIVE PROMOTION:  NO
```

**Research question**: does the HIGH-risk common-stock short-horizon condition retain its
+30m separation on an independent forward sample?

**Primary next gate**: `coverage repaired AND N >= 60`. No parameter tuning.

### KEEP-2 — Post-Reclaim-Pullback Hypothesis

**Q18 is the evaluation consumer, not the primary alpha program.** Correct chain:

```
Q8 primary evidence → post-reclaim-pullback hypothesis → Q18 bounded evaluation
consumer / promotion review
```

```
~35 independent episodes, three independent reconstructions
+30m net ≈ +0.33% ~ +0.42%,  PF ≈ 2 ~ 3

episode-level persisted outcomes = 0
coverage max ≈ 85.71%   (required = 90%)

HYPOTHESIS:      EDGE_PROMISING
Q18 ROLE:        EVALUATION CONSUMER
PROMOTION:       BLOCKED
```

Active research keeps the **hypothesis** alive; it does not promote Q18 into a new primary
evidence source.

### KEEP-3 — Q10 Index Lead-Market / Reaction / Timing

One active track, three distinguished sub-studies:

```
Calc F: US lead-market → Samsung/Hynix opening reaction     (~13 days)
  EDGE:            INSUFFICIENT_EVIDENCE
  DISCRIMINATOR:   UNKNOWN / NO_REPEATABLE_SEPARATION_YET

Calc G: US/global context → KOSPI/KOSDAQ reaction           (~11 usable days)
  EDGE:            INSUFFICIENT_EVIDENCE
  DISCRIMINATOR:   UNKNOWN / NO_REPEATABLE_SEPARATION_YET

Calc H: directional call → entry-timing policies            (<=3 obs per policy)
  EDGE:            INSUFFICIENT_EVIDENCE
  DISCRIMINATOR:   UNKNOWN
```

The underlying research review does not establish a promising discriminator for Calc F/G/H
at this sample size — the reason this track stays `KEEP` is continued prospective evidence
collection, not an already-promising discriminator. Continue forward collection. No policy
winner declared. No policy removed yet.

### KEEP-4 — Opening Conditional Rank / Short-Horizon Reactivation

**Does not include** the broad Rank-1 hypothesis (that is `DEPRECATE_REVIEW`, §5). Active
scope is the narrow conditional population only:

```
Opening 1B/1C short-horizon behavior
Conditional Rank-1 lanes: IMMEDIATE_OPENING_PROBE, CONFIRMED_RECURRENT_RANK,
                          DISLOCATION_REBOUND
Persistence / momentum-confirmation conditions
```

```
Broad finding:   Rank-1 alone is NOT alpha.
Active question: does Rank-1 + a specific context/discriminator produce repeatable
                 short-horizon separation? — specifically:
                 repeated Rank-1 persistence, completed 1-min momentum,
                 overextension, relative-volume overheating
```

Do not overstate the short-horizon finding using D+5 outcomes: the overall D+5 close
averaged −2.43% despite the positive short-horizon +30m aggregate (see §5 Retained Controls
for the separately-tracked non-alpha control roles).

### KEEP-5 — Regime / Context Discriminator Validation

Independently re-validate the context variables already showing `SEPARATION_SHOWN`:

```
asset class x HIGH risk, VWAP subtype, candidate source family,
Rank-1 persistence, completed 1-min momentum, relative-volume inversion,
price-extension inversion
```

And evaluate the still-`CONTEXT_FIELD_ONLY` macro bundle **only as an attached shadow
discriminator test on existing episode outcomes** — never as a new trading lane:

```
KOSPI, KOSDAQ, S&P500, Nasdaq, Dow, VIX, DXY, USD/KRW, USD/JPY,
bond yields, SOX, NVIDIA, Micron
```

No new trading lane is created under this track.

---

## 4. WATCH — Exactly 3

### WATCH-1 — Q12 Calc2 (BTC → Woori)

Exact hypothesis: `BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1`.

```
fully-confirming live path:  never fired
key cells:                   N = 1~2
recent controlled attempts:  ~0  (INPUT_MISSING / WINDOW_CLOSED dominant)
```

The prerequisite is not alpha tuning — it is **08:55 BTC point-in-time input reliability**.

**WATCH trigger**: `input pipeline healthy AND >= 20 clean prospective sessions`. No
hypothesis-verdict expansion before then.

### WATCH-2 — Q9 Post-Exit Timing

Research substance and the canonical-adapter status are kept separate.

```
Largest cross-day study: 100 comparable trades
avg ≈ -0.241%,  PF ≈ 0.67
```

Current evidence does **not** support unconditional longer holding. However, no standing
cross-day aggregator exists yet, and exit_reason/regime/symbol breakdowns remain thin.

**Status**: `WATCH, negative-leaning`. Not actively expanded into a new hold-extension
research program until an aggregator + breakdown exist.

**Canonical clarification**: the current frozen Q9 canonical horizon set is
`+5m / +15m / +30m / +60m / EOD`. Legacy source placeholders that also carried `T+1`/`T+2`
are historical/legacy fields only and are **not** part of the current canonical Q9 horizon
profile — they must never be cited as if they were.

### WATCH-3 — Strategist Stage-2 Effectiveness

```
Current aggregate: R2 - R1 ≈ -0.447pp
```

Confounded by elapsed time, market-data refresh, Scanner reranking, and the LLM's own
tactical refresh simultaneously. **No "Strategist helps/hurts" conclusion is authorized** from
this aggregate.

**WATCH trigger**: a deconfounded paired experiment exists. Re-evaluate only then.

---

## 5. Retained Controls — Not Active Alpha Tracks (3)

These do **not** count toward the 5 KEEP tracks.

### Q11 — Opportunity Engine

**Correct role**: `PRIMARY NEGATIVE_CONTROL / SHADOW EVIDENCE`. Never described as
`CONSUMER_ONLY` — Q11 generates its own evidence as an intentional negative-control research
probe, not as a passive consumer of another family's output.

```
Current state: not profitable, not promoted, functioning as intended.
Status:         RETAIN AS NEGATIVE CONTROL. Not an alpha candidate.
```

### Q15 — Runner-Up Candidate Filtering

```
Role: defensive / structural loss-suppression policy.
```

Q15 is not an alpha claim. It is retained, but never described as a "proven positive-EV
strategy."

### Q10 Semiconductor

```
Correct role: Samsung/Hynix momentum/volume baseline control.
```

**Important**: this is **not** a US lead-market study. It must never be cited as SOX/Nasdaq/
NVIDIA/Micron lead-market evidence — that hypothesis is tested only by KEEP-3 (Q10 Index
Calc F/G). Q10 Semiconductor is retained as a baseline/control, not an independent active
alpha track. Rename/rescope of its documentation is a separate backlog item, not performed
by this freeze.

---

## 6. DEPRECATE_REVIEW (5)

Removed from the independent active-research-track list. None of these are code deletions.

1. **Q8 broad relaxation candidates** — retained as historical rejection/observability
   evidence (feeds Q9-adjacent research context); not re-opened without new qualifying
   evidence.
2. **Q16 ATR/volatility directional-edge proxy** — retained as prohibition/negative-
   discriminator evidence (documents that ATR/volatility magnitude does not substitute for
   real directional expectancy).
3. **Broad Opening Rank-1 entry** — superseded by KEEP-4's narrow conditional framing; the
   broad hypothesis itself is not re-opened.
4. **Five-session broad Rank-1 review** — closed window, retained as the authoritative
   record of that closure, not re-opened.
5. **Q12 Calc1 as an independent hypothesis** — it is a direct reuse of the Q10 Samsung/Hynix
   baseline engine, not independent BTC-Woori evidence; retained only as shared-baseline
   infrastructure.

---

## 7. BLOCKED (7)

```
Q9 canonical adapter
  reason: exit_price_authority provenance not persisted

Q11 legacy v1
  reason: observed_price not persisted (v2 repair exists, SOL pre-audit pass,
          Codex ratification pending)

Q12 Calc3
  reason: legacy completeness contradiction (row-count vs. exact-grid)
          + Friday->Monday timing-alignment validity defect

Q18 promotion-grade tracking
  reason: episode-level forward-outcome persistence missing from the canonical artifact

rank1_feature_mart canonicalization
  reason: extended-horizon / dual-cost / fallback architecture mismatch with the frozen
          UEF contract

Feedback / Memory causal effectiveness
  reason: paired feedback-disabled control does not exist;
          performance_delta_pct = None, usefulness_score = None,
          causal_claim_allowed = False (hardcoded at the code level)

Controlled Mock Lane 2026-08-28 -> 2026-09-07
  reason: scanner-rank attribution contamination (fixed going forward; historical window
          excluded from any rank-attribution conclusion)
```

The Feedback/Memory **mechanism** itself is not being disabled by this freeze — only its
**causal effectiveness claim** is BLOCKED until a paired control exists.

---

## 8. Research Quality Gates

No hypothesis may skip this sequence going forward:

```
interesting pattern
  -> discriminator candidate
  -> predefined hypothesis
  -> prospective evidence
  -> clean provenance
  -> cost-aware evaluation
  -> repeatability across sessions
  -> EDGE_CONFIRMED
  -> separate live-promotion review
```

`EDGE_PROMISING` is not live-promotion authority at any point in this chain.

---

## 9. No New Q Rule

Effective from this freeze: **no new Q number by default.** A newly discovered data source
does not by itself justify a new Q / new agent / new lane. First determine whether it belongs
inside one of the 5 KEEP tracks or 3 WATCH items above. Only a genuinely new physical
hypothesis (not representable inside any existing track) goes through an architecture review
before any new Q number is created.

---

## 10. Evidence Contamination Policy

The following windows/fields must never be reused uncritically as clean forward-edge proof:

```
2026-07-17                        stale mock-broker fills
through 2026-07-30                pytest synthetic data written into production evidence paths
2026-08-28 -> 2026-09-07          controlled-lane scanner-rank attribution defect
2026-07-24                        invalid low-coverage Q17 day (75.47% < 95% required)
Q12 Calc3                         Friday -> Monday timing-alignment defect
```

Any future historical recompute (UEF-5 preparation) must separate **validated clean
evidence** from **quarantined/invalid evidence**. This document does not itself implement a
Clean Evidence Registry — that implementation is a future UEF-5 preparation backlog item.

---

## 11. Portfolio Summary Table

| Track | Portfolio Status | Role | Current Edge Verdict | Discriminator Verdict | Current N/Days | Main Blocker | Next Gate |
|---|---|---|---|---|---:|---|---|
| Short Alpha Discriminator (KEEP-1) | KEEP | Active alpha candidate | EDGE_PROMISING | FOUND | N=39 | snapshot coverage 58.6%<80% | coverage repaired AND N>=60 |
| Post-Reclaim-Pullback Hypothesis (KEEP-2) | KEEP | Active hypothesis (Q18=consumer) | EDGE_PROMISING | FOUND | ~35 episodes | episode-outcome persistence=0; coverage 85.71%<90% | schema fix + coverage>=90% |
| Q10 Index Calc F (KEEP-3) | KEEP-3 SUBSTUDY | Sub-study: US->Samsung/Hynix | INSUFFICIENT_EVIDENCE | UNKNOWN / NO_REPEATABLE_SEPARATION_YET | ~13 days | sample too small | more forward days |
| Q10 Index Calc G (KEEP-3) | KEEP-3 SUBSTUDY | Sub-study: US/global->KOSPI/KOSDAQ | INSUFFICIENT_EVIDENCE | UNKNOWN / NO_REPEATABLE_SEPARATION_YET | ~11 usable days | sample too small + verification gaps | more forward days |
| Q10 Index Calc H (KEEP-3) | KEEP-3 SUBSTUDY | Sub-study: directional call->entry timing | INSUFFICIENT_EVIDENCE | UNKNOWN | <=3 obs/policy | setup rarity | many more real trading days |
| Opening Conditional Rank / Reactivation (KEEP-4) | KEEP | Narrow conditional track | EDGE_PROMISING (short-horizon lanes) | FOUND (conditional lanes) | 49-196 episodes (lane-dependent) | small-N lanes; D+5 not durable | independent replication of conditional lanes |
| Regime / Context Discriminator Validation (KEEP-5) | KEEP | Validation track | mixed | FOUND (several) / UNKNOWN (macro bundle) | N=8-52 per variable | macro bundle never shadow-tested | first shadow test of macro bundle |
| Q12 Calc2 BTC->Woori (WATCH-1) | WATCH | Hypothesis test | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | 15 days; key cells N=1-2 | chronic INPUT_MISSING | input pipeline healthy AND N>=20 clean sessions |
| Q9 Post-Exit Timing (WATCH-2) | WATCH | Research substance (adapter separate) | INSUFFICIENT_EVIDENCE (negative-leaning) | NO_DISCRIMINATOR (no breakdown yet) | N=100 trades (largest study) | no standing aggregator/breakdown | build aggregator + breakdown |
| Strategist Stage-2 (WATCH-3) | WATCH | Effectiveness question | INSUFFICIENT_EVIDENCE (confounded) | DISCRIMINATOR_ONLY (weak/confounded) | 75 independent pairs/7 days | confounded by time/data-refresh | deconfounded paired experiment |
| Q11 Opportunity Engine | RETAINED CONTROL | Primary negative control | N/A (functioning as intended) | N/A | 61 days (no cumulative) | no cumulative aggregator | N/A |
| Q15 Candidate Filtering | RETAINED CONTROL | Defensive/structural policy | N/A (not an edge claim) | DISCRIMINATOR_ONLY | 17 trades (canonical root-cause) | narrow evidence at selection | N/A |
| Q10 Semiconductor | RETAINED CONTROL | Momentum/volume baseline | INSUFFICIENT_EVIDENCE (own hypothesis) | N/A — does not test lead-market hypothesis | 96 rows/20 trades (1 day) | no cumulative aggregator; naming/scope | rename/rescope (backlog) |
| Q8 broad relaxation candidates | DEPRECATE_REVIEW | Historical rejection evidence | NO_EDGE_DETECTED | DISCRIMINATOR_ONLY (rejection) | 1,802 trusted obs/4 days | negative after cost; cost-floor bug | none (closed) |
| Q16 ATR/volatility proxy | DEPRECATE_REVIEW | Prohibition evidence | NO_EDGE_DETECTED | DISCRIMINATOR_ONLY (negative) | 156 rejections/83 obs/5 days | one-day-outlier-driven | none (closed) |
| Broad Opening Rank-1 entry | DEPRECATE_REVIEW | Rejected broad hypothesis | NO_EDGE_DETECTED | N/A | N=196 episodes (broad pop.) | negative every intraday checkpoint | none (narrow lanes -> KEEP-4) |
| Five-session broad Rank-1 review | DEPRECATE_REVIEW | Closed window review | NO_EDGE_DETECTED | N/A | N=21/4-5 days | heterogeneous distribution | none (closed) |
| Q12 Calc1 (independent hypothesis) | DEPRECATE_REVIEW | Shared baseline reuse | CONSUMER_ONLY | N/A | N/A | not independent evidence | none (relabel only) |
| Q9 canonical adapter | BLOCKED | Canonicalization | N/A (infra) | N/A | N/A | exit_price_authority not persisted | future additive source-contract change |
| Q11 legacy v1 | BLOCKED | Canonicalization | N/A (infra) | N/A | N/A | observed_price not persisted | Codex ratification of v2 |
| Q12 Calc3 | BLOCKED | Canonicalization + research validity | N/A | N/A | N/A | completeness contradiction + timing defect | architecture decision + timing-logic fix |
| Q18 promotion-grade tracking | BLOCKED | Schema gap | EDGE_PROMISING (hypothesis, see KEEP-2) | FOUND | ~35 episodes | episode-outcome persistence missing | schema fix |
| rank1_feature_mart canonicalization | BLOCKED | Canonicalization | PRIMARY EVIDENCE (substance ok) | N/A | 196 episodes/52 days/80 symbols | dual-cost/extended-horizon shape mismatch | architecture decision |
| Feedback/Memory causal effectiveness | BLOCKED | Causal-claim gate | INSUFFICIENT_EVIDENCE | INSUFFICIENT_EVIDENCE | 0 (hardcoded None) | no paired control exists | design + run paired control |
| Controlled Mock Lane 2026-08-28->09-07 | BLOCKED | Contamination window | N/A | N/A | window-scoped | scanner-rank attribution contamination | exclude window from rank-attribution conclusions |

---

## 12. What This Freeze Does Not Mean

```
KEEP                != profitable
WATCH               != failed
DEPRECATE_REVIEW    != delete code
BLOCKED             != no research value
UEF FROZEN          != alpha confirmed
EDGE_PROMISING      != live-ready
```

---

## 13. Resume Plan (next development cycle, priority order)

```
1. Clean Evidence Registry / contamination boundary
2. UEF-5 Historical Recompute preparation
3. Short Alpha Discriminator coverage repair
4. Post-reclaim-pullback future episode-outcome persistence
5. Q10 Index continued forward collection
6. First macro/regime shadow discriminator evaluation
```

`UEF-5` remains **NOT STARTED**.

---

## 14. Source Corrections Applied (relative to `tmp/research_review_2026-09-16.md`)

- **Q11**: the source review's shorthand `CONSUMER_ONLY` is corrected here to
  `PRIMARY NEGATIVE_CONTROL / SHADOW EVIDENCE` — Q11 generates its own evidence as a
  deliberate negative-control research probe, not a passive consumer of another family.
- **Q18**: the source review's framing risked implying Q18 itself is the promising alpha
  program. Corrected: the **post-reclaim-pullback hypothesis** is `EDGE_PROMISING`; **Q18** is
  the bounded evaluation-consumer / promotion-review role that tests it, per
  `docs/research/uef4_legacy_family_inventory.md` §5.9's own "no primary evidence of their
  own" classification for Q18.
- **Q9**: legacy source placeholders historically also carried `T+1`/`T+2` checkpoint slots.
  These are legacy/historical fields only. The current frozen canonical Q9 horizon profile is
  `+5m/+15m/+30m/+60m/EOD` — the two must not be conflated in any research conclusion.

---

## 15. Final Governance Statement

```
As of 2026-09-16, no trading hypothesis has earned EDGE_CONFIRMED status.

The research portfolio is intentionally narrowed.

The system will prioritize clean prospective evidence for five active research tracks,
observe three watch items, retain three non-alpha controls, and avoid reopening
deprecated or blocked work without new qualifying evidence.

No live strategy logic change is authorized by this freeze.
```
