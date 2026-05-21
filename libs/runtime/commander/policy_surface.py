from __future__ import annotations

from typing import Literal


RuntimeMode = Literal["graph_spine", "decision_packet", "integrated_chain"]
RuntimePhase = Literal["preopen", "session", "closeout"]


PRE_BUY_STRATEGIST_REFRESH_MIN_CACHE_AGE_SEC = 300
PRE_BUY_STRATEGIST_REFRESH_READINESS_THRESHOLD = 0.80
SELECTED_SYMBOL_TACTICAL_REFRESH_MIN_CACHE_AGE_SEC = 300
SELECTED_SYMBOL_TACTICAL_REFRESH_MIN_SCORE = 0.88
DEFAULT_BUY_CLOSEOUT_CUTOFF_MIN = 15
PRE_BUY_STRATEGIST_REFRESH_FORCE_SIGNALS = frozenset(
    {
        "prior_cycle_buy_intent",
        "became_ready_this_cycle",
    }
)
OPEN_POSITION_STRATEGIST_REFRESH_COOLDOWN_SEC = 900

COMMANDER_OWNED_POLICY_FIELDS = [
    "universe.asset_type",
    "reporter.ai_review.enabled",
    "reporter.trade_report.enabled",
    "reporter.trade_report.generate_on_open",
    "strategist.runtime.strict_mode",
    "strategist.runtime.allow_legacy_rule",
    "strategist.runtime.allow_legacy_strategy_v1",
    "strategist.memory_feedback.enabled",
    "strategist.performance_memory.enabled",
    "strategist.performance_memory.persist_enabled",
    "strategist.memory_usage.disabled",
    "strategist.reporter_feedback_mode",
    "commander.route.monitor_only_when_holding",
    "commander.route.cached_strategist_when_flat",
    "commander.route.post_scanner_refresh_enabled",
    "commander.route.pre_entry_exit_sweep_enabled",
    "commander.memory_usage.disabled",
    "monitor.exit.enabled",
    "monitor.exit.eod_flat.enabled",
    "monitor.entry.block_buy_when_open_position",
    "monitor.entry.buy_closeout_cutoff_min",
    "monitor.entry.position_sizing.enabled",
    "monitor.memory_bias.observation_only",
    "monitor.entry.scoring.enabled",
    "monitor.entry.scoring.shadow_mode",
    "scanner.memory_bias.observation_only",
]
COMMANDER_OWNED_UNIVERSE_POLICY_FIELDS = [
    "universe.asset_type",
]
COMMANDER_OWNED_SCANNER_POLICY_FIELDS = [
    "scanner.source.type",
    "scanner.kiwoom.strict_only",
    "scanner.fallback.block_static_when_empty",
    "scanner.kiwoom.live_fetch",
    "scanner.kiwoom.include_change_rate",
    "scanner.policy.market_representative_guard",
]
COMMANDER_OWNED_NUMERIC_POLICY_FIELDS = [
    "execution.cooldowns.post_exit_sec",
    "execution.cooldowns.sell_sec",
    "monitor.hold.min_hold_seconds",
    "monitor.exit.confirm_ticks",
    "monitor.exit.eod_flat.cutoff_min",
    "monitor.entry.buy_closeout_cutoff_min",
    "scanner.candidate.top_pool",
    "scanner.kiwoom.condition_limit",
    "monitor.entry.scoring.threshold",
    "monitor.entry.position_sizing.risk_per_trade_ratio",
    "monitor.entry.position_sizing.position_notional_ratio",
    "monitor.entry.position_sizing.max_position_qty",
    "monitor.entry.position_sizing.max_position_notional",
    "monitor.entry.position_sizing.min_position_qty",
    "monitor.entry.position_sizing.lot_size",
    "strategist.memory_feedback.recent_runs",
]
COMMANDER_OWNED_LLM_POLICY_FIELDS = [
    "llm.strategist.profile",
    "llm.reporter.intraday.profile",
    "llm.reporter.daily.profile",
]
COMMANDER_OWNED_LLM_EXECUTION_POLICY_FIELDS = [
    "llm.execution_profile.profile_name",
    "llm.execution_profile.temperature",
    "llm.execution_profile.max_tokens",
    "llm.execution_profile.timeout_sec",
    "llm.execution_profile.retry.max_attempts",
    "llm.execution_profile.retry.backoff_sec",
    "llm.strategist.execution_profile.name",
    "llm.strategist.execution_profile.temperature",
    "llm.strategist.execution_profile.max_tokens",
    "llm.strategist.execution_profile.timeout_sec",
    "llm.strategist.execution_profile.retry_max",
    "llm.reporter.intraday.execution_profile.name",
    "llm.reporter.intraday.execution_profile.temperature",
    "llm.reporter.intraday.execution_profile.max_tokens",
    "llm.reporter.daily.execution_profile.name",
    "llm.reporter.daily.execution_profile.temperature",
    "llm.reporter.daily.execution_profile.max_tokens",
]

ENTRY_CONTROL_POOL_EXPAND_BLOCKERS = frozenset(
    {
        "too_extended_from_vwap",
        "still_overextended_after_pullback",
        "breakout_not_ready",
        "below_vwap_reclaim_not_ready",
        "pullback_below_vwap_reclaim_not_ready",
        "reclaim_not_ready",
        "entry_wait",
        "wait_for_confirmation",
    }
)
ENTRY_CONTROL_DYNAMIC_BAND_BLOCKERS = frozenset(
    {
        "too_extended_from_vwap",
        "still_overextended_after_pullback",
    }
)
CANDIDATE_WATCH_DEFAULT_CASCADE_ALLOWED_REASONS = (
    "too_extended_from_vwap",
    "breakout_not_ready",
    "below_vwap_reclaim_not_ready",
    "pullback_below_vwap_reclaim_not_ready",
)
CANDIDATE_WATCH_DEFAULT_CASCADE_BLOCKED_REASONS = (
    "cost_filter_failed",
    "cost_adjusted_edge_not_ready",
    "directional_edge_evidence_missing",
    "estimated_gross_edge_missing",
    "volume_confirmation_missing",
    "volume_insufficient",
    "volume_missing",
    "pullback_not_mature",
    "risk_policy_block",
    "closeout_window",
    "open_position_present",
    "daily_loss_limit",
    "broker_truth_mismatch",
    "data_quality_guard",
    "buy_blocked_post_exit_cooldown",
    "buy_blocked_closeout_window",
)

COMMANDER_TEMPORARY_RUNTIME_ENV_DEFAULTS = {
    "COMMANDER_POST_SCANNER_REFRESH_ENABLED": "true",
    "MEMORY_BIAS_OBSERVATION_ONLY": "true",
    "USE_STRATEGY_MEMORY_FEEDBACK": "false",
    "USE_STRATEGY_PERFORMANCE_MEMORY": "false",
    "COMMANDER_MEMORY_USAGE_DISABLED": "true",
    "STRATEGIST_MEMORY_USAGE_DISABLED": "true",
    "STRATEGY_MEMORY_PERSIST_ENABLED": "false",
}

PRE_ENTRY_EXIT_SWEEP_TRANSIENT_KEYS = (
    "selected",
    "scanner_output",
    "intents",
    "monitor_output",
    "monitor_entry",
    "monitor_exit",
    "monitor_entry_decision_detail",
    "monitor_exit_decision_detail",
    "monitor_action_decision",
    "monitor_entry_blocker_surface",
    "monitor_feature_hydration",
    "decision",
    "decision_reason",
    "decision_packet",
)
