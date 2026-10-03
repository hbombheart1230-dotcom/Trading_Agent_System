# 2026-08-25 Q12 Trend and Rank-1 Observability

## Scope

This patch is additive observability and shadow evaluation only. It does not
change Q9, Scanner ranking, Strategist authority, Commander approval, Monitor,
orders, or execution.

## Rank-1 Evidence

- Point-in-time market snapshots now record freshness, timeline size, eligible
  snapshot count, and the delay to the next post-decision observation.
- The next observation is explicitly marked
  `POST_DECISION_OBSERVABILITY_ONLY` and cannot become a decision feature.
- Scanner quote snapshots now distinguish an unavailable quote payload from a
  payload that exists but does not contain best bid/ask fields.
- Quote provider provenance is retained in the compact Q9 candidate snapshot.

## Q12 Recent BTC Trend

The existing Q12 v2 and `BTC_STRONG_BULL_LOCAL_CONFIRMATION_V1` contracts are
unchanged. A separate additive shadow variant is added:

`BTC_PERSISTENT_TREND_LOCAL_CONFIRMATION_V1`

It observes:

- 15-minute, 60-minute, 4-hour, and 24-hour direction alignment
- positive 5-minute momentum ratio over the recent 60 minutes
- 15-minute momentum acceleration or deceleration
- realized recent volatility
- drawdown from the recent 6-hour and 24-hour highs
- Woori local volume/breakout and VWAP/short-MA confirmation

The variant rejects an extended BTC rise when short-term momentum is fading.
It is shadow-only, creates no `OrderIntent`, and has an independent forward
performance summary.

The `2026-08-25` regeneration is labeled `historical_reconstruction`. Formal
prospective shadow evidence starts on `2026-08-26`, and each decision stores
both `prospective_start_day` and `evidence_phase` so the two evidence classes
cannot be silently mixed.
