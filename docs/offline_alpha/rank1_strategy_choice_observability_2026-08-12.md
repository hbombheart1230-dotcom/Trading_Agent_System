# Rank-1 Strategy Choice Observability

## Purpose

This patch makes Strategist playbook and tactic concentration measurable
without changing any trading behavior.

It separates four concepts that were previously easy to conflate:

1. deterministic market playbook before the LLM
2. playbook requested by the LLM
3. final market playbook
4. the observed setup of the Scanner Rank-1 candidate

The output is evaluation-only. It does not modify Strategist prompts, tactic
scores, Scanner ranking, Monitor entry/exit, Commander approval, or execution.

## Observation Model

Each canonical Rank-1 episode now includes
`strategy_choice_observation` with:

### Playbook choice

* `pre_llm_playbook`
* `llm_requested_playbook`
* `requested_playbook_source`
* `final_playbook`
* `changed_from_pre_llm`

### Generation provenance

* `DETERMINISTIC_MARKET_FRAME`
* `LLM_MARKET_FRAME`
* `TACTICAL_REFRESH_INHERITED_MARKET_FRAME`
* `CACHED_OR_SKIPPED_FRAME`
* `MISSING_CANONICAL_EVIDENCE`

The report also retains the LLM model, status, temperature, fallback state,
and Commander invocation hint when available.

### Tactic option surface

All 12 catalog tactics are listed for every observed episode. Each tactic is
marked as:

* `SCORED`
* `NOT_SCORED_BY_CURRENT_MODEL`

The selected tactic, playbook-default tactic, eligible tactic family, rejected
reason, and whether the selected tactic merely equals the playbook default are
stored separately.

The source does not currently persist whether a selected tactic originated
from deterministic fallback, LLM choice, or manual override. The read model
therefore records `selection_source_status=NOT_EXPLICITLY_PERSISTED` instead of
inferring authority.

### Candidate setup alignment

The Rank-1 candidate setup is compared with the selected market tactic family:

* `MATCH`: same setup/tactic family
* `COMPATIBLE`: direction supports the tactic but does not prove its trigger
* `MISMATCH`: candidate and selected tactic belong to different families
* `INSUFFICIENT_EVIDENCE`: liquidity-only or unclassified candidate

This is not a correctness label. A broad market pullback frame can coexist
with a momentum candidate. The label exists to measure whether that
combination performs differently.

`candidate_tactical_recommendation` lists observation-only tactic candidates
associated with the setup. It is never sent to Scanner, Monitor, Commander, or
execution.

## Reconstructed Baseline

The 2026-06 through 2026-08 Rank-1 mart contains 61 episodes with canonical
Strategist evidence.

| Field | Distribution |
| --- | --- |
| Market playbook | pullback 29, defensive 23, breakout 9 |
| Tactic | vwap reclaim 29, defensive observe 23, volume breakout 8, opening range breakout 1 |
| Candidate setup | directional breadth 25, liquidity-only 25, fresh change 5, unclassified 6 |
| Default tactic selected | 53 / 61 |
| Catalog tactics | 12 |
| Tactics scored by current Strategist model | 7 |

The baseline confirms that tactic concentration is primarily structural: most
observed decisions inherit the playbook default and five catalog tactics are
not scored by the current Strategist model.

Initial alignment results are descriptive and may contain small-sample and
outlier effects:

| Alignment | Independent N | +15m average | +30m average | EOD average |
| --- | ---: | ---: | ---: | ---: |
| COMPATIBLE | 14 | +2.5885% | +2.4283% | +2.1773% |
| MISMATCH | 16 | +2.4548% | +2.0966% | -1.2658% |
| INSUFFICIENT_EVIDENCE | 31 | -0.0228% | -0.1883% | +0.1639% |

The `MISMATCH` group is not automatically bad. Its positive short-horizon and
negative EOD shape is evidence that candidate setup and holding horizon may be
more important than forcing one market playbook onto the candidate.

## Artifacts

* `reports/evaluation/feature_mart/opening_rank1/feature_mart.json`
* `reports/evaluation/feature_mart/opening_rank1/strategy_setup_alignment/strategy_setup_alignment_cumulative.json`
* `reports/evaluation/feature_mart/opening_rank1/strategy_setup_alignment/strategy_setup_alignment_cumulative.md`
* `reports/evaluation/feature_mart/opening_rank1/strategy_setup_alignment/daily/YYYY-MM-DD/strategy_setup_alignment.json`
* `reports/evaluation/feature_mart/opening_rank1/strategy_setup_alignment/daily/YYYY-MM-DD/strategy_setup_alignment.md`

Normal closeout rebuilds the feature mart, so future eligible days accumulate
under the same observation schema. No prospective contract or behavior rule is
reset by this additive patch.
