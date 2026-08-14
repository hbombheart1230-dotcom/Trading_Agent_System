# Offline Alpha Research

This folder contains research that runs outside the live multi-agent trading
path.

Rules:

- no order execution
- no runtime behavior change
- fixed hypotheses and gates before outcome review
- historical minute reconstruction
- live and mock cost bases kept separate
- only evidence-ready candidates may move to controlled adoption

Current research:

- `opening_rank1_controlled_probe_2026-08-14.md`
  - starts one mock-only controlled behavior experiment on 2026-08-17
  - permits only Scanner Rank-1 `DIRECTIONAL_BREADTH` or
    `FRESH_CHANGE_ACTIVATION` from 09:00 through 09:20
  - keeps cost, chart hard-floor, position, risk-off, order, and exit safety intact
  - caps the lane at one 25%-size probe per day for five full trading days
  - does not promote broad opening entry or alter official policy

- `canonical_rank1_feature_mart_2026-08-11.md`
  - freezes one June-August Rank-1 feature and horizon contract
  - separates Scanner suitability, Monitor entry timing, and Strategist horizon evidence
  - permits at most two prospective shadow candidates and no runtime behavior change

- `rank1_fixed_candidate_prospective_shadow_2026-08-11.md`
  - freezes the selected branches and contract hash through 2026-08-11
  - starts a five-valid-day prospective window on 2026-08-12
  - integrates observation-only generation into normal closeout
  - never enables a behavior patch automatically

- `rank1_fresh_change_activation_shadow_2026-08-12.md`
  - keeps the 2026-08-11 fixed candidate contract unchanged
  - adds a separate `R1_FRESH_CHANGE_ACTIVATION_V1` observer
  - restores canonical Strategist/Scanner and point-in-time chart provenance
  - requires 5 independent day-symbols and stops after at most 10 valid days
  - keeps theme, breadth, chart, recurrence, and quote fields descriptive only

- `rank1_strategy_choice_observability_2026-08-12.md`
  - separates deterministic, LLM-requested, and final market playbooks
  - exposes all 12 tactic options and identifies unscored catalog tactics
  - records whether the selected tactic is only the playbook default
  - compares market tactic family with the observed Rank-1 candidate setup
  - writes daily and cumulative alignment reports without behavior changes

- `active_research_register_2026-08-07.md`
  - current authority for active work and stopping rules
  - Priority 1: latent-reactivation fresh-trigger forwards, decision at 12
  - Priority 2: same-symbol reentry provenance, decision at 10 clean profit reentries
  - opening conditional lanes continue as non-blocking background observation

- `five_session_closure_2026-08-07.md`
  - closes the fixed 2026-08-03 through 2026-08-07 window without extension
  - rejects broad opening Rank-1 entry as a live behavior
  - retains the three conditional lanes as observer evidence only
  - completes Monitor-NOOP attribution with 188 episodes and 96.81% coverage
  - selects `RETAIN_CURRENT_MONITOR_GATES`; no behavior patch and no P3 run

- `reports/evaluation/offline_alpha/monitor_noop_attribution/`
  - deduplicates 363 repeated Q9 cycles into contiguous decision episodes
  - compares gross, live-cost, and mock-cost outcomes by blocker
  - adds first-day-symbol sensitivity metrics to prevent repeated-symbol inflation
  - is observation-only and reproducible from its frozen candle cache

- `reports/evaluation/opening_rank1_shadow/latent_watch/latent_reactivation_forward.*`
  - anchors a later fresh signal to the next tradable one-minute open
  - records gross/live/mock +5m/+15m/+30m/+60m/EOD outcomes
  - excludes trigger days whose opening evidence is not `VALID`

- `reports/evaluation/same_symbol_sequences/`
  - records day-symbol trade order, cumulative PnL, giveback, and Q9 provenance
  - counts only profit reentries that the current loss-reentry block would permit

- `canonical_execution_plan_2026-08-06.md`
  - frozen definitions and historical operating schedule after reconstruction
  - closes the old three-day integration check
  - fixes the active five-session decision window at 2026-08-03 through 2026-08-07
  - keeps the separate 25-episode/10-day broad Rank-1 control gate in the background
  - permits at most one behavior-patch candidate after the five-session close

- `post_reclaim_offline_research_2026-07-30.md`
  - target: `confirmed_post_reclaim_pullback`
  - result: `RETAIN_SHADOW`
  - performance gates passed
  - fixed +30m forward coverage gate failed at 85.71%

- `post_reclaim_executable_policy_v0_2026-07-30.md`
  - frozen policy: 12/15 pre-entry print density and +30m exit
  - train: June 2026
  - validation: July 2026
  - result: `REJECT`
  - no live behavior change

- `alpha_hypothesis_competition_v1_contract_2026-07-30.md`
  - frozen comparison contract for three independent hypotheses

- `alpha_hypothesis_competition_v1_result_2026-07-30.md`
  - 102/102 historical symbols complete
  - all three hypotheses rejected
  - no shadow or live integration

- `structural_alpha_batch1_contract_2026-07-30.md`
  - frozen contract for cross-sectional relative strength, sector leadership,
    and volatility contraction breakout
  - Q9 pre-Strategist Top 5 is the point-in-time universe

- `structural_alpha_batch1_result_2026-07-30.md`
  - H4 cross-sectional relative strength: rejected
  - H5 point-in-time sector leader: not testable with current historical
    artifacts
  - H6 volatility contraction breakout: rejected
  - no threshold tuning and no live or shadow integration

- `structural_alpha_batch2_contract_2026-07-30.md`
  - final frozen batch: market-shock reversal, oversold mean reversion, and
    trend pullback resumption

- `structural_alpha_batch2_result_2026-07-30.md`
  - H7, H8, and H9 rejected
  - no threshold tuning and no live or shadow integration

- `structural_alpha_search_closure_2026-07-30.md`
  - finite six-hypothesis search closed
  - zero eligible candidates, five rejects, one not testable

- `existing_evidence_mining_contract_2026-07-31.md`
  - fixed contract for exhausting retained Q9, quant-shadow, minute-cache, and
    actual-trade evidence before collecting another broad live window

- `existing_evidence_mining_result_2026-07-31.md`
  - 13,174 Q9 windows, 5,292 reconstructed episodes, 1,937 quant-shadow
    episodes, and 105 realized trades reviewed
  - entry uses the first minute candle strictly after the decision
  - broad captured candidate universe remains negative after 0.28% cost
  - one bounded discovery candidate retained:
    `OPEN_0_20_RANK1_30M`
  - candidate is future-confirmation-only; no runtime behavior change

- `opening_rank1_prospective_validation_2026-07-31.md`
  - freezes the prospective definition and decision gates for
    `OPEN_0_20_RANK1_30M`
  - first eligible day: 2026-08-03
  - minimum evidence: 25 observed episodes across at least 10 trading days
  - a pass authorizes controlled shadow review only

The prospective broad-control gate above does not extend the now-closed five-session
decision window. See `canonical_execution_plan_2026-08-06.md` for the schedule
boundary, `five_session_closure_2026-08-07.md` for the final decision, and
`active_research_register_2026-08-07.md` for the current queue.
