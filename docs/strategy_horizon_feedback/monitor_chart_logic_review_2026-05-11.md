# Monitor Chart Logic Review - 2026-05-11

## Purpose

This note summarizes whether the current Monitor entry/exit logic is close to human chart reading, and what should be improved later. This is documentation only; no runtime patch is included here.

## Current Assessment

The Monitor is a reasonable deterministic rule engine, but it is not yet equivalent to a human reading a chart.

It currently uses:

- recent-high breakout through `recent_high` / `breakout_level`
- VWAP hold and VWAP reclaim
- VWAP distance / overextension band
- pullback depth from recent high
- current volume versus recent average volume
- confidence score around breakout or pullback-volume path
- previous close / open gap / previous-close distance as observation fields
- prior bar low, VWAP breakdown, intraday low break, and peak drawdown for exits
- cost-aware entry and exit filters

This is enough to block many weak or expensive setups, but it is still closer to "mechanical signal confirmation" than "human chart reading".

## What Is Not Yet Strong Enough

- Support/resistance is mostly single-level based, not zone based.
- Prior lows are used more for exit protection than for entry support confirmation.
- Candlestick quality is not yet a primary gate. Long upper wick, strong body close, rejection candle, and failed breakout candle quality are not deeply scored.
- Breakout-retest-hold-reacceleration is not yet treated as a first-class high-quality setup.
- Prior day high/low, session open, opening range high/low, and intraday pivot levels are not yet central scoring levels.
- Volume confirmation exists, but volume exhaustion and tape weakening are more exit-side than entry-side.
- The logic can tell whether a breakout or pullback condition is present, but it is weaker at telling whether the setup is a good chart location versus a chase.

## Improvement Priorities For Later Patch

1. Structural level surface
   - Add previous day high/low, session open, session high/low, 5-minute and 15-minute opening range high/low, pivot high/low.

2. Support/resistance zone model
   - Represent levels as zones with touch count, last touch age, distance, break/reject state, and volume-at-level context.

3. Candle quality model
   - Add body ratio, wick ratios, close location, breakout candle strength, rejection candle detection, and failed-breakout detection.

4. Breakout-retest pattern
   - Promote `breakout -> retest -> hold -> re-acceleration` into a separate high-quality entry path.

5. Faster failed-breakout exit
   - If a breakout entry loses breakout level, VWAP, or session open quickly after entry, tighten exit handling.

## Working Conclusion

The current Monitor is directionally rational, but it is still a first-stage rules engine. To improve win rate, the next meaningful step is not simply loosening thresholds. The next step should be upgrading chart context quality so the system can distinguish a clean setup from a late chase.
