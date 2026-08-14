from __future__ import annotations

from typing import Any, Mapping

from .contracts import COHORTS, MEMORY_CLEAN, SYMBOL_MEMORY_MISMATCH


def _pct(numerator: int, denominator: int) -> str:
    return f"{(100.0 * numerator / denominator):.2f}%" if denominator else "-"


def _metric(value: Any) -> str:
    if value is None:
        return "-"
    if value == float("inf"):
        return "inf"
    return str(value)


def render_markdown(payload: Mapping[str, Any]) -> str:
    total = int(payload.get("stage2_call_count") or 0)
    cohorts = payload.get("cohorts") if isinstance(payload.get("cohorts"), Mapping) else {}
    lines = [
        "# Q9 Memory Contamination Review",
        "",
        f"- Period: **{payload.get('start_day')} ~ {payload.get('end_day')}**",
        f"- Stage-2 tactical refresh calls: **{total:,}**",
        f"- Q9-linked calls: **{int(payload.get('q9_linked_count') or 0):,}**",
        f"- Trusted realized trades linked: **{int(payload.get('trusted_trade_count') or 0):,}**",
        "- Behavior change: **none; historical reclassification only**",
        "",
        "## Cohort Summary",
        "",
        "| Cohort | Calls | Share | Q9 linked | Approve | Veto | No-trade | Tightened | Trades | Win rate | Avg return | PF |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cohort in COHORTS:
        row = cohorts.get(cohort) if isinstance(cohorts.get(cohort), Mapping) else {}
        count = int(row.get("stage2_call_count") or 0)
        win_rate = row.get("trade_win_rate")
        lines.append(
            "| {cohort} | {count:,} | {share} | {linked:,} | {approve:,} | {veto:,} | "
            "{no_trade:,} | {tightened:,} | {trades:,} | {win_rate} | {avg} | {pf} |".format(
                cohort=cohort,
                count=count,
                share=_pct(count, total),
                linked=int(row.get("q9_linked_count") or 0),
                approve=int(row.get("commander_approve_count") or 0),
                veto=int(row.get("commander_veto_count") or 0),
                no_trade=int(row.get("commander_no_trade_count") or 0),
                tightened=int(row.get("entry_policy_tightened_count") or 0),
                trades=int(row.get("trusted_trade_count") or 0),
                win_rate=(f"{100.0 * float(win_rate):.1f}%" if win_rate is not None else "-"),
                avg=_metric(row.get("trade_avg_return_pct")),
                pf=_metric(row.get("trade_profit_factor")),
            )
        )

    clean = cohorts.get(MEMORY_CLEAN) if isinstance(cohorts.get(MEMORY_CLEAN), Mapping) else {}
    mismatch = (
        cohorts.get(SYMBOL_MEMORY_MISMATCH)
        if isinstance(cohorts.get(SYMBOL_MEMORY_MISMATCH), Mapping)
        else {}
    )
    lines += [
        "",
        "## Monthly Distribution",
        "",
        "| Month | Stage-2 | Q9 linked | Clean | Symbol mismatch | Stale/contradictory | Insufficient | Mismatch tightened |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload.get("by_month") or []:
        counts = row.get("cohort_counts") if isinstance(row.get("cohort_counts"), Mapping) else {}
        lines.append(
        f"| {row.get('month')} | {int(row.get('stage2_call_count') or 0):,} | "
            f"{int(row.get('q9_linked_count') or 0):,} | {int(counts.get('MEMORY_CLEAN') or 0):,} | "
            f"{int(counts.get('SYMBOL_MEMORY_MISMATCH') or 0):,} | "
            f"{int(counts.get('STALE_OR_CONTRADICTORY_MEMORY') or 0):,} | "
            f"{int(counts.get('INSUFFICIENT_MEMORY_EVIDENCE') or 0):,} | "
            f"{int(row.get('mismatch_tightened_count') or 0):,} |"
        )
    forward = payload.get("forward_comparison")
    forward = forward if isinstance(forward, Mapping) else {}
    forward_cohorts = forward.get("by_cohort")
    forward_cohorts = forward_cohorts if isinstance(forward_cohorts, Mapping) else {}
    lines += [
        "",
        "## Q9 Forward Comparison By Memory Cohort",
        "",
        f"- Directly linked decision windows: **{int(forward.get('linked_decision_count') or 0):,}**",
        f"- Cost applied to B/C policy returns: **{_metric(forward.get('cost_pct'))}%** "
        f"(`{forward.get('cost_source') or 'unknown'}`, {int(forward.get('cost_profile_sample_count') or 0):,} samples)",
        "- Strategist delta is B minus A on the same decision window; Commander delta is C policy net return minus B net return.",
        "- Commander no-trade is valued at 0%; therefore C-B primarily measures cost/loss avoidance and is not pure Commander selection alpha.",
        "",
        "| Cohort | Horizon | Decisions | A/B pairs | B avg gross | B-A avg | B>A rate | C comparisons | C policy avg net | C-B avg | C>B rate |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for cohort in (MEMORY_CLEAN, SYMBOL_MEMORY_MISMATCH):
        cohort_forward = forward_cohorts.get(cohort)
        cohort_forward = cohort_forward if isinstance(cohort_forward, Mapping) else {}
        decision_count = int(cohort_forward.get("linked_decision_count") or 0)
        for row in cohort_forward.get("horizons") or []:
            b_rate = row.get("strategist_positive_delta_rate")
            c_rate = row.get("commander_positive_delta_rate")
            lines.append(
                f"| {cohort} | {row.get('horizon')} | {decision_count:,} | "
                f"{int(row.get('paired_scanner_strategist_count') or 0):,} | "
                f"{_metric(row.get('strategist_avg_gross_return_pct'))} | "
                f"{_metric(row.get('strategist_minus_scanner_avg_pct'))} | "
                f"{(f'{100.0 * float(b_rate):.1f}%' if b_rate is not None else '-')} | "
                f"{int(row.get('commander_comparison_count') or 0):,} | "
                f"{_metric(row.get('commander_policy_avg_net_return_pct'))} | "
                f"{_metric(row.get('commander_minus_strategist_avg_pct'))} | "
                f"{(f'{100.0 * float(c_rate):.1f}%' if c_rate is not None else '-')} |"
            )
    lines += [
        "",
        "## Interpretation",
        "",
        "1. Scanner P/A, raw Rank-1 prices, and offline forward-return studies are not rewritten by this review.",
        "2. Strategist B and Commander C should be evaluated twice: all rows for historical behavior, and MEMORY_CLEAN only for agent-effect estimates.",
        "3. SYMBOL_MEMORY_MISMATCH rows remain valid records of what the runtime did, but they are excluded from claims about pure Strategist or Commander quality.",
        "4. STALE_OR_CONTRADICTORY_MEMORY is assigned only when directional evidence was actually visible; stale legacy Reporter feedback already marked excluded is not treated as contamination.",
        "5. INSUFFICIENT_MEMORY_EVIDENCE is not folded into clean or contaminated performance.",
        "6. Forward results are shadow observations; they do not replace broker-truth realized PnL.",
        "",
        "## Decision Impact",
        "",
        f"- Clean Stage-2 calls: **{int(clean.get('stage2_call_count') or 0):,}**",
        f"- Confirmed cross-symbol calls: **{int(mismatch.get('stage2_call_count') or 0):,}**",
        f"- Cross-symbol calls with tightened entry policy: **{int(mismatch.get('entry_policy_tightened_count') or 0):,}**",
        "- A policy delta in a contaminated call proves exposure, not that memory alone caused the eventual return.",
        "- Trade performance is linked only when run ID and Stage-2 target symbol both match; reused strategy anchors are excluded.",
        "",
        "## Required Use",
        "",
        "- Preserve all existing P/A and offline alpha conclusions.",
        "- Recompute B/C summaries with `cohort == MEMORY_CLEAN` before using them for promotion or deprecation.",
        "- Keep contaminated rows as a separate operational-defect cohort.",
        "- Do not restart Q8/Q9 validation from zero solely because of this defect.",
        "",
        "## Mismatch Examples",
        "",
        "| Day | Run | Target | Memory | Stage-2 decision | Commander | Tightened |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in list(payload.get("mismatch_examples") or [])[:20]:
        lines.append(
            f"| {row.get('day')} | {str(row.get('run_id') or '')[:12]} | {row.get('target_symbol')} | "
            f"{row.get('memory_symbol')} | {row.get('stage2_decision') or '-'} | "
            f"{row.get('commander_decision') or '-'} | {bool(row.get('entry_policy_tightened'))} |"
        )
    return "\n".join(lines) + "\n"
