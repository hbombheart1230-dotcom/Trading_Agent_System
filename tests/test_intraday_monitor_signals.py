from libs.runtime.intraday_monitor_signals import (
    _build_monitor_policy_aware_gating,
    _build_monitor_policy_interpretation,
    evaluate_intraday_entry_signal,
    resolve_intraday_entry_policy,
)
from libs.runtime.monitor_policy import MonitorEntryPolicy, normalize_monitor_entry_policy_schema
from pathlib import Path


def _rows_breakout() -> list[dict]:
    return [
        {"open": 100.0, "high": 100.4, "low": 99.8, "close": 100.2, "volume": 900, "vwap": 100.0},
        {"open": 100.2, "high": 100.8, "low": 100.1, "close": 100.7, "volume": 980, "vwap": 100.3},
        {"open": 100.7, "high": 101.1, "low": 100.5, "close": 100.9, "volume": 1020, "vwap": 100.5},
        {"open": 100.9, "high": 101.3, "low": 100.7, "close": 101.1, "volume": 1100, "vwap": 100.7},
        {"open": 101.1, "high": 101.4, "low": 100.9, "close": 101.2, "volume": 1080, "vwap": 100.9},
        {"open": 101.2, "high": 101.9, "low": 101.0, "close": 101.8, "volume": 2500, "vwap": 101.2},
    ]


def _rows_pullback_rebound() -> list[dict]:
    return [
        {"open": 100.0, "high": 100.5, "low": 99.9, "close": 100.4, "volume": 1000, "vwap": 100.1},
        {"open": 100.4, "high": 101.1, "low": 100.3, "close": 101.0, "volume": 1050, "vwap": 100.5},
        {"open": 101.0, "high": 101.8, "low": 100.9, "close": 101.6, "volume": 1100, "vwap": 100.9},
        {"open": 101.6, "high": 101.7, "low": 100.4, "close": 100.8, "volume": 950, "vwap": 100.9},
        {"open": 100.8, "high": 100.9, "low": 99.7, "close": 100.2, "volume": 980, "vwap": 100.6},
        {"open": 100.2, "high": 101.3, "low": 100.1, "close": 101.1, "volume": 1500, "vwap": 100.7},
    ]


def _rows_breakout_reclaim_near_ready() -> list[dict]:
    rows = _rows_breakout()
    rows[-1]["vwap"] = 101.96
    return rows


def _rows_daily_seed_like() -> list[dict]:
    start_ts = 1_710_000_000
    rows: list[dict] = []
    closes = [100.0, 101.5, 102.0, 103.0, 102.8, 104.0]
    for idx, close in enumerate(closes[:-1]):
        rows.append(
            {
                "ts": start_ts + idx * 86400,
                "open": close - 0.5,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": 1_000_000 + idx * 20_000,
                "vwap": close - 0.2,
            }
        )
    rows.append(
        {
            "ts": start_ts + len(closes[:-1]) * 86400,
            "open": 104.0,
            "high": 104.0,
            "low": 104.0,
            "close": 104.0,
            "volume": 1.0,
            "vwap": 103.4,
        }
    )
    return rows


def test_intraday_entry_triggers_on_breakout_vwap_hold_and_volume_confirmation() -> None:
    out = evaluate_intraday_entry_signal(_rows_breakout())

    assert out["evaluated"] is True
    assert out["triggered"] is True
    assert out["pattern"] == "breakout_vwap_hold"
    assert out["entry_condition_path"] == "breakout_path"
    assert "breakout_path" in list(out.get("entry_condition_paths_passed") or [])
    assert "volume_confirmation" in list(out.get("signal_chain") or [])
    assert float((out.get("metrics") or {}).get("volume_ratio") or 0.0) >= 1.15
    scores = out.get("condition_scores") or {}
    assert float(scores.get("confidence_score") or 0.0) >= float(scores.get("confidence_threshold") or 0.0)


def test_intraday_entry_triggers_on_pullback_rebound_setup() -> None:
    out = evaluate_intraday_entry_signal(
        _rows_pullback_rebound(),
        policy={"entry_breakout_lookback": 4, "entry_volume_ratio_min": 0.95},
        frame={"playbook": "pullback"},
    )

    assert out["evaluated"] is True
    assert out["triggered"] is True
    assert out["pattern"] == "pullback_vwap_reclaim"
    assert out["entry_condition_path"] == "pullback_volume_path"
    assert "pullback_rebound" in list(out.get("signal_chain") or [])
    assert "pullback_mature" in list(out.get("passed_checks") or [])
    assert out.get("primary_failure_axis") == "confirmed_entry"
    thresholds = out.get("thresholds") or {}
    assert float(thresholds.get("max_extended_from_vwap_pct") or 0.0) >= 0.05
    assert float(thresholds.get("pullback_max_pct") or 0.0) >= 0.06


def test_intraday_entry_rejects_overextended_breakout() -> None:
    rows = _rows_breakout()
    rows[-1]["close"] = 103.2
    rows[-1]["high"] = 103.4
    rows[-1]["vwap"] = 101.1
    out = evaluate_intraday_entry_signal(rows, policy={"entry_max_extended_from_vwap_pct": 0.02})

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["reason"] == "too_extended_from_vwap"
    assert out.get("primary_failure_axis") == "overextension"
    assert "extension_ok" in list(out.get("failed_checks") or [])


def test_intraday_entry_allows_breakout_path_without_strict_volume_confirmation() -> None:
    rows = _rows_breakout()
    rows[-1]["volume"] = 900
    out = evaluate_intraday_entry_signal(rows, policy={"entry_volume_ratio_min": 1.0})

    assert out["evaluated"] is True
    assert out["triggered"] is True
    assert out["decision"] == "BUY"
    assert out["entry_condition_path"] == "breakout_path"
    assert (out.get("metrics") or {}).get("volume_ok") is False
    assert out["reason"] in {
        "breakout_above_recent_high_with_vwap_structure_confirmation",
        "breakout_above_recent_high_with_vwap_reclaim_confirmation",
        "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation",
    }


def test_intraday_entry_rejects_failed_reclaim() -> None:
    rows = _rows_pullback_rebound()
    rows[-1]["close"] = 100.1
    rows[-1]["high"] = 100.4
    rows[-1]["vwap"] = 100.8
    out = evaluate_intraday_entry_signal(rows, frame={"playbook": "pullback"})

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "below_vwap_reclaim_not_ready"
    assert out.get("primary_failure_axis") == "vwap_relationship"
    assert float(out.get("reclaim_distance_to_ready") or 0.0) < 0.0
    assert 0.0 <= float(out.get("vwap_reclaim_progress") or 0.0) <= 1.0
    assert float(out.get("transition_readiness_score") or 0.0) < 1.0
    transition_trace = out.get("entry_transition_trace") or {}
    assert transition_trace.get("last_blocking_axis") == "vwap_relationship"
    assert transition_trace.get("became_ready_this_cycle") is False


def test_intraday_entry_breakout_path_still_blocks_when_reclaim_gate_is_not_ready() -> None:
    rows = _rows_breakout()
    rows[-1]["close"] = 101.8
    rows[-1]["high"] = 101.9
    rows[-1]["vwap"] = 102.2

    out = evaluate_intraday_entry_signal(rows, policy={"entry_volume_ratio_min": 1.2})

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["entry_condition_path"] == ""
    assert out["reason"] == "below_vwap_reclaim_not_ready"
    assert "reclaim_gate_ok" in list(out.get("failed_checks") or [])


def test_intraday_entry_rejects_overextended_pullback_even_after_rebound() -> None:
    rows = _rows_pullback_rebound()
    rows[-1]["close"] = 106.0
    rows[-1]["high"] = 106.2
    rows[-1]["vwap"] = 100.7
    out = evaluate_intraday_entry_signal(
        rows,
        policy={"entry_max_extended_from_vwap_pct": 0.02},
        frame={"playbook": "pullback"},
    )

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "still_overextended_after_pullback"
    assert out.get("primary_failure_axis") == "overextension"
    margins = out.get("threshold_margins") or {}
    ext = margins.get("extended_from_vwap_pct") or {}
    assert float(ext.get("actual") or 0.0) > float(ext.get("max") or 0.0)


def test_intraday_entry_rejects_deeply_broken_pullback_structure() -> None:
    rows = _rows_pullback_rebound()
    rows[4]["low"] = 94.8
    rows[4]["close"] = 99.8
    rows[-1]["close"] = 100.9
    rows[-1]["high"] = 101.0
    rows[-1]["vwap"] = 100.5
    out = evaluate_intraday_entry_signal(
        rows,
        policy={"entry_pullback_max_pct": 0.03},
        frame={"playbook": "pullback"},
    )

    assert out["evaluated"] is True
    assert out["triggered"] is False
    assert out["reason"] == "no_valid_pullback_structure"
    assert out.get("primary_failure_axis") == "pullback_structure"
    assert "pullback_not_too_deep" in list(out.get("failed_checks") or [])


def test_intraday_entry_pullback_can_pass_without_strict_volume_spike_if_reclaim_is_clean() -> None:
    rows = _rows_pullback_rebound()
    rows[-1]["volume"] = 900
    out = evaluate_intraday_entry_signal(rows, frame={"playbook": "pullback"})

    assert out["evaluated"] is True
    assert out["triggered"] is True
    assert out["decision"] == "BUY"
    assert out["pattern"] == "pullback_vwap_reclaim"
    assert (out.get("metrics") or {}).get("reclaim_gate_ok") is True
    assert (out.get("metrics") or {}).get("volume_ok") is True
    scores = out.get("condition_scores") or {}
    assert bool(scores.get("confidence_gate_ok")) is True
    assert float(out.get("transition_readiness_score") or 0.0) >= 0.55
    transition_trace = out.get("entry_transition_trace") or {}
    assert transition_trace.get("became_ready_this_cycle") is False


def test_intraday_entry_pullback_policy_is_looser_than_breakout_policy() -> None:
    breakout = resolve_intraday_entry_policy(frame={"playbook": "breakout"})
    pullback = resolve_intraday_entry_policy(frame={"playbook": "pullback"})

    assert float(pullback.get("max_extended_from_vwap_pct") or 0.0) > float(breakout.get("max_extended_from_vwap_pct") or 0.0)
    assert float(pullback.get("pullback_max_pct") or 0.0) > float(breakout.get("pullback_max_pct") or 0.0)
    assert float(pullback.get("volume_ratio_min") or 0.0) <= float(breakout.get("volume_ratio_min") or 0.0)


def test_intraday_entry_pullback_uses_live_shallow_pullback_floor() -> None:
    pullback = resolve_intraday_entry_policy(
        policy={"entry_pullback_min_pct": 0.012},
        frame={"playbook": "pullback"},
    )

    assert float(pullback.get("pullback_min_pct") or 0.0) == 0.008


def test_intraday_entry_pullback_defensive_guidance_stays_realistic() -> None:
    pullback = resolve_intraday_entry_policy(
        frame={
            "playbook": "pullback",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
        }
    )

    assert float(pullback.get("max_extended_from_vwap_pct") or 0.0) >= 0.05
    assert float(pullback.get("volume_ratio_min") or 0.0) <= 1.0


def test_intraday_entry_pullback_defensive_guidance_matches_live_relaxed_thresholds() -> None:
    pullback = resolve_intraday_entry_policy(
        policy={
            "entry_volume_ratio_min": 0.72,
            "entry_pullback_min_pct": 0.012,
        },
        frame={
            "playbook": "pullback",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
        }
    )

    assert float(pullback.get("volume_ratio_min") or 0.0) == 0.68
    assert float(pullback.get("pullback_min_pct") or 0.0) == 0.008


def test_intraday_entry_policy_is_official_object_with_live_defaults() -> None:
    resolved = resolve_intraday_entry_policy()

    assert isinstance(resolved, MonitorEntryPolicy)
    assert resolved.timeframe_minutes == 1
    assert resolved.breakout_lookback == 5
    assert resolved.volume_lookback == 5
    assert float(resolved.volume_ratio_min) == 0.68
    assert float(resolved.max_extended_from_vwap_pct) == 0.13
    assert float(resolved.pullback_min_pct) == 0.008
    assert float(resolved.pullback_max_pct) == 0.07


def test_intraday_entry_runtime_no_longer_uses_monitor_entry_env_lookup() -> None:
    source = Path("libs/runtime/intraday_monitor_signals.py").read_text(encoding="utf-8")

    legacy_env_keys = [
        "MONITOR_ENTRY_TIMEFRAME_MINUTES",
        "MONITOR_ENTRY_BREAKOUT_LOOKBACK",
        "MONITOR_ENTRY_VOLUME_LOOKBACK",
        "MONITOR_ENTRY_VOLUME_RATIO_MIN",
        "MONITOR_ENTRY_MIN_EXTENDED_FROM_VWAP_PCT",
        "MONITOR_ENTRY_MAX_EXTENDED_FROM_VWAP_PCT",
        "MONITOR_ENTRY_PULLBACK_MIN_PCT",
        "MONITOR_ENTRY_PULLBACK_MAX_PCT",
        "MONITOR_ENTRY_RECLAIM_TOLERANCE_PCT",
        "MONITOR_ENTRY_BREAKOUT_BUFFER_PCT",
        "MONITOR_ENTRY_INTENT_COOLDOWN_SEC",
    ]

    for key in legacy_env_keys:
        assert key not in source


def test_intraday_entry_defensive_stack_stays_usable_without_becoming_loose() -> None:
    defensive = resolve_intraday_entry_policy(
        frame={
            "playbook": "defensive",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "medium",
        }
    )

    assert float(defensive.get("max_extended_from_vwap_pct") or 0.0) >= 0.03
    assert float(defensive.get("max_extended_from_vwap_pct") or 0.0) <= 0.05
    assert float(defensive.get("volume_ratio_min") or 0.0) <= 1.1


def test_intraday_entry_does_not_reapply_strategy_frame_when_policy_is_already_resolved() -> None:
    resolved = resolve_intraday_entry_policy(
        policy={"entry_volume_ratio_min": 0.68, "entry_max_extended_from_vwap_pct": 0.13},
        frame={
            "playbook": "defensive",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
        },
    )

    out = evaluate_intraday_entry_signal(
        _rows_breakout(),
        policy=resolved,
        frame={
            "playbook": "defensive",
            "monitor_guidance": "defensive_exit",
            "risk_tone": "conservative",
            "trade_aggressiveness": "low",
        },
    )

    applied = out.get("applied_policy") or {}
    assert round(float(applied.get("volume_ratio_min") or 0.0), 2) == 0.75
    assert float(applied.get("max_extended_from_vwap_pct") or 0.0) == 0.05


def test_intraday_entry_waits_when_minute_candles_missing() -> None:
    out = evaluate_intraday_entry_signal([])

    assert out["evaluated"] is False
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "minute_candle_missing"
    metrics = out.get("metrics") or {}
    assert metrics.get("bar_count") == 0


def test_intraday_entry_waits_when_candle_data_incomplete() -> None:
    out = evaluate_intraday_entry_signal(_rows_breakout()[:3])

    assert out["evaluated"] is False
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "data_incomplete"
    metrics = out.get("metrics") or {}
    assert int(metrics.get("bar_count") or 0) == 3


def test_intraday_entry_rejects_non_intraday_seed_series_as_minute_data() -> None:
    out = evaluate_intraday_entry_signal(_rows_daily_seed_like(), current_price=104.0)

    assert out["evaluated"] is False
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "minute_candle_missing"
    metrics = out.get("metrics") or {}
    assert float(metrics.get("inferred_spacing_minutes") or 0.0) >= 1000.0
    assert metrics.get("series_class") == "daily_or_higher"


def test_intraday_entry_scoring_disabled_keeps_legacy_decision(monkeypatch) -> None:
    monkeypatch.delenv("MONITOR_SCORING_ENABLED", raising=False)
    monkeypatch.delenv("MONITOR_SCORING_SHADOW_MODE", raising=False)
    monkeypatch.delenv("MONITOR_ENTRY_SCORE_THRESHOLD", raising=False)

    out = evaluate_intraday_entry_signal(_rows_breakout())

    assert out["triggered"] is True
    assert out["decision"] == "BUY"
    assert out["scoring_mode"] == "disabled"
    assert out["legacy_entry_decision"] == "BUY"
    assert out["scoring_entry_decision"] == "BUY"
    assert out["hard_filter_passed"] is True
    assert float(out.get("total_score") or 0.0) >= 3.0


def test_intraday_entry_policy_interpretation_is_empty_safe_without_explicit_policy() -> None:
    out = evaluate_intraday_entry_signal(_rows_breakout())

    interpretation = out.get("policy_interpretation") or {}
    trace = out.get("policy_interpreter_trace") or {}
    summary = out.get("policy_alignment_summary") or {}
    assert interpretation.get("policy_available") is False
    assert interpretation.get("entry_style") is None
    assert interpretation.get("required_checks") == []
    assert interpretation.get("preferred_checks") == []
    assert interpretation.get("relaxable_checks") == []
    assert interpretation.get("blockers") == []
    assert interpretation.get("notes") == []
    assert trace.get("available") is False
    assert trace.get("policy_available") is False
    assert (trace.get("alignment_summary") or {}).get("policy_alignment_state") is None
    assert summary.get("available") is False
    assert summary.get("alignment_state") is None
    assert summary.get("primary_blocker") is None
    assert summary.get("top_failed_required_checks") == []
    assert summary.get("top_relaxable_gaps") == []


def test_intraday_entry_policy_interpretation_maps_pullback_policy_hints_without_changing_buy() -> None:
    out = evaluate_intraday_entry_signal(
        _rows_pullback_rebound(),
        policy={
            "entry_volume_ratio_min": 0.68,
            "require_vwap_reclaim": True,
            "require_rebound": True,
        },
        frame={"playbook": "pullback"},
    )

    interpretation = out.get("policy_interpretation") or {}
    trace = out.get("policy_interpreter_trace") or {}
    summary = out.get("policy_alignment_summary") or {}
    assert interpretation.get("policy_available") is True
    assert interpretation.get("entry_style") == "pullback"
    assert "reclaim_gate_ok" in list(interpretation.get("required_checks") or [])
    assert "rebound_ok" in list(interpretation.get("required_checks") or [])
    assert "pullback_ok" in list(interpretation.get("preferred_checks") or [])
    assert "volume_ok" in list(interpretation.get("preferred_checks") or [])
    assert "breakout_ok" in list(interpretation.get("relaxable_checks") or [])
    assert ((interpretation.get("priority_hints") or {}).get("pullback_priority")) == "high"
    assert "pullback_ok" in list(((interpretation.get("evidence_focus") or {}).get("primary")) or [])
    required_rows = {row["name"]: row for row in list((trace.get("check_status") or {}).get("required") or [])}
    preferred_rows = {row["name"]: row for row in list((trace.get("check_status") or {}).get("preferred") or [])}
    relaxable_rows = {row["name"]: row for row in list((trace.get("check_status") or {}).get("relaxable") or [])}
    blocker_rows = {row["name"]: row for row in list((trace.get("check_status") or {}).get("blockers") or [])}
    assert trace.get("available") is True
    assert required_rows["reclaim_gate_ok"]["status"] == "pass"
    assert required_rows["rebound_ok"]["status"] == "pass"
    assert preferred_rows["pullback_ok"]["status"] == "pass"
    assert preferred_rows["volume_ok"]["status"] == "pass"
    assert relaxable_rows["breakout_ok"]["status"] in {"fail", "pass"}
    assert blocker_rows["too_extended"]["status"] == "inactive"
    assert (trace.get("alignment_summary") or {}).get("policy_alignment_state") == "aligned"
    assert summary.get("available") is True
    assert summary.get("alignment_state") == "aligned"
    assert summary.get("primary_blocker") is None
    assert summary.get("top_failed_required_checks") == []
    assert "breakout_ok" in list(summary.get("top_relaxable_gaps") or [])
    assert out["triggered"] is True
    assert out["decision"] == "BUY"


def test_monitor_policy_interpretation_prefers_explicit_selected_policy_fields() -> None:
    interpretation = _build_monitor_policy_interpretation(
        effective_policy=MonitorEntryPolicy.from_mapping(
            {
                "entry_volume_ratio_min": 1.0,
                "require_vwap_reclaim": True,
                "policy_source": "strategist",
            }
        ),
        frame={"playbook": "pullback"},
        policy_contract={
            "selected_source": "commander_applied_policy",
            "selected_policy": {
                "entry_style": "breakout",
                "required_checks": ["volume_ok"],
                "preferred_checks": ["breakout_ok"],
                "relaxable_checks": ["reclaim_gate_ok"],
                "blockers": ["policy_disabled"],
                "priority_hints": {
                    "volume_priority": "high",
                    "reclaim_priority": "normal",
                    "breakout_priority": "high",
                    "pullback_priority": "low",
                },
                "evidence_focus": {
                    "primary": ["breakout_ok"],
                    "secondary": ["reclaim_gate_ok"],
                },
                "notes": ["explicit_breakout_bias"],
                "policy_source": "strategist",
                "policy_adjustments": ["explicit_policy_contract"],
            },
        },
    )

    assert interpretation.get("entry_style") == "breakout"
    assert interpretation.get("contract_source") == "commander_applied_policy"
    assert interpretation.get("policy_schema_available") is True
    assert interpretation.get("policy_schema_version") == "monitor_entry_policy_schema_candidate.v1"
    assert interpretation.get("interpretation_basis") == "explicit_policy"
    assert interpretation.get("required_checks") == ["volume_ok"]
    assert interpretation.get("preferred_checks") == ["breakout_ok"]
    assert interpretation.get("relaxable_checks") == ["reclaim_gate_ok"]
    assert interpretation.get("blockers") == ["policy_disabled"]
    assert ((interpretation.get("priority_hints") or {}).get("breakout_priority")) == "high"
    assert ((interpretation.get("evidence_focus") or {}).get("primary")) == ["breakout_ok"]
    assert interpretation.get("notes") == ["explicit_breakout_bias"]


def test_monitor_policy_interpretation_keeps_playbook_fallback_when_selected_policy_has_no_explicit_fields() -> None:
    interpretation = _build_monitor_policy_interpretation(
        effective_policy=MonitorEntryPolicy.from_mapping(
            {
                "entry_volume_ratio_min": 0.68,
                "require_vwap_reclaim": True,
                "require_rebound": True,
                "policy_source": "strategist",
            }
        ),
        frame={"playbook": "pullback"},
        policy_contract={
            "selected_source": "commander_applied_policy",
            "selected_policy": {
                "volume_ratio_min": 0.68,
                "policy_source": "strategist",
            },
        },
    )

    assert interpretation.get("entry_style") == "pullback"
    assert interpretation.get("policy_schema_available") is False
    assert interpretation.get("policy_schema_version") == "monitor_entry_policy_schema_candidate.v1"
    assert interpretation.get("interpretation_basis") == "fallback_playbook"
    assert "reclaim_gate_ok" in list(interpretation.get("required_checks") or [])
    assert "rebound_ok" in list(interpretation.get("required_checks") or [])
    assert "pullback_ok" in list(interpretation.get("preferred_checks") or [])


def test_intraday_entry_explicit_policy_contract_changes_interpretation_basis_without_forcing_decision() -> None:
    baseline = evaluate_intraday_entry_signal(
        _rows_pullback_rebound(),
        policy={
            "entry_volume_ratio_min": 0.68,
            "require_vwap_reclaim": True,
            "require_rebound": True,
        },
        frame={"playbook": "pullback"},
    )
    explicit = evaluate_intraday_entry_signal(
        _rows_pullback_rebound(),
        policy={
            "entry_volume_ratio_min": 0.68,
            "require_vwap_reclaim": True,
            "require_rebound": True,
        },
        frame={"playbook": "pullback"},
        policy_contract={
            "selected_source": "commander_applied_policy",
            "selected_policy": {
                "entry_style": "pullback",
                "notes": ["explicit_entry_style"],
            },
        },
    )

    assert baseline.get("triggered") is True
    assert baseline.get("decision") == "BUY"
    assert explicit.get("triggered") == baseline.get("triggered")
    assert explicit.get("decision") == baseline.get("decision")
    assert (explicit.get("policy_interpretation") or {}).get("policy_schema_available") is True
    assert (explicit.get("policy_interpretation") or {}).get("policy_schema_version") == "monitor_entry_policy_schema_candidate.v1"
    assert (explicit.get("policy_interpretation") or {}).get("interpretation_basis") == "mixed"


def test_normalize_monitor_entry_policy_schema_stabilizes_loose_selected_policy_fields() -> None:
    schema = normalize_monitor_entry_policy_schema(
        {
            "entry_style": "breakout",
            "required_checks": ("volume_ok",),
            "preferred_checks": {"breakout_ok", "reclaim_gate_ok"},
            "relaxable_checks": "pullback_ok",
            "blockers": ["policy_disabled"],
            "priority_hints": {"volume_priority": "high"},
            "evidence_focus": {
                "primary": "breakout_ok",
                "secondary": ("reclaim_gate_ok",),
            },
            "policy_adjustments": "explicit_policy_contract",
            "notes": "explicit_breakout_bias",
        }
    )

    assert schema.get("schema_version") == "monitor_entry_policy_schema_candidate.v1"
    assert schema.get("available") is True
    assert schema.get("entry_style") == "breakout"
    assert schema.get("required_checks") == ["volume_ok"]
    assert set(schema.get("preferred_checks") or []) == {"breakout_ok", "reclaim_gate_ok"}
    assert schema.get("relaxable_checks") == ["pullback_ok"]
    assert schema.get("blockers") == ["policy_disabled"]
    assert schema.get("priority_hints") == {
        "volume_priority": "high",
        "reclaim_priority": None,
        "breakout_priority": None,
        "pullback_priority": None,
    }
    assert schema.get("evidence_focus") == {
        "primary": ["breakout_ok"],
        "secondary": ["reclaim_gate_ok"],
    }
    assert schema.get("policy_adjustments") == ["explicit_policy_contract"]
    assert schema.get("notes") == ["explicit_breakout_bias"]
    assert "required_checks" in list(schema.get("raw_keys") or [])


def test_intraday_entry_policy_interpreter_trace_can_show_primary_blocker_without_changing_wait() -> None:
    rows = _rows_pullback_rebound()
    rows[-1]["close"] = 100.1
    rows[-1]["high"] = 100.4
    rows[-1]["vwap"] = 100.8

    out = evaluate_intraday_entry_signal(
        rows,
        policy={
            "entry_volume_ratio_min": 0.68,
            "require_vwap_reclaim": True,
            "require_rebound": True,
        },
        frame={"playbook": "pullback"},
    )

    trace = out.get("policy_interpreter_trace") or {}
    summary = out.get("policy_alignment_summary") or {}
    required_rows = {row["name"]: row for row in list((trace.get("check_status") or {}).get("required") or [])}
    assert required_rows["reclaim_gate_ok"]["status"] == "fail"
    assert (trace.get("alignment_summary") or {}).get("policy_alignment_state") == "misaligned"
    assert (trace.get("alignment_summary") or {}).get("primary_blocker") == "reclaim_gate_ok"
    assert summary.get("alignment_state") == "misaligned"
    assert summary.get("primary_blocker") == "reclaim_gate_ok"
    assert "reclaim_gate_ok" in list(summary.get("top_failed_required_checks") or [])
    assert isinstance(summary.get("summary_notes"), list)
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "below_vwap_reclaim_not_ready"


def test_intraday_entry_policy_aware_gating_stays_empty_safe_without_policy_hint() -> None:
    out = evaluate_intraday_entry_signal(_rows_breakout_reclaim_near_ready())

    gating = out.get("policy_aware_gating") or {}
    assert gating.get("available") is False
    assert gating.get("applied") is False
    assert gating.get("relaxations_applied") == []
    assert out["legacy_entry_decision"] == "WAIT"
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"


def test_intraday_entry_policy_aware_gating_blocks_when_required_check_fails() -> None:
    rows = _rows_pullback_rebound()
    rows[-1]["close"] = 100.1
    rows[-1]["high"] = 100.4
    rows[-1]["vwap"] = 100.8

    out = evaluate_intraday_entry_signal(
        rows,
        policy={
            "entry_volume_ratio_min": 0.68,
            "require_vwap_reclaim": True,
            "require_rebound": True,
        },
        frame={"playbook": "pullback"},
    )

    gating = out.get("policy_aware_gating") or {}
    assert gating.get("available") is True
    assert gating.get("applied") is False
    assert "reclaim_gate_ok" in list(gating.get("required_failures") or [])
    assert "reclaim_gate_ok" in list(gating.get("blocked_by_required") or [])
    assert out["legacy_entry_decision"] == "WAIT"
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"


def test_intraday_entry_policy_aware_gating_can_relax_breakout_reclaim_when_near_ready() -> None:
    out = evaluate_intraday_entry_signal(
        _rows_breakout_reclaim_near_ready(),
        policy={
            "entry_volume_ratio_min": 1.0,
            "require_vwap_reclaim": True,
        },
        frame={"playbook": "breakout"},
    )

    gating = out.get("policy_aware_gating") or {}
    assert out["legacy_entry_decision"] == "WAIT"
    assert gating.get("available") is True
    assert gating.get("applied") is True
    assert "reclaim_gate_ok" in list(gating.get("relaxations_applied") or [])
    assert "reclaim_relaxed_near_ready" in list(gating.get("applied_hints") or [])
    assert out["triggered"] is True
    assert out["decision"] == "BUY"
    assert out["pattern"] == "breakout_policy_reclaim_near_ready"
    assert out["entry_condition_path"] == "breakout_path"
    assert out["reason"] == "breakout_above_recent_high_with_policy_reclaim_near_ready"


def test_monitor_policy_aware_gating_helper_does_not_relax_when_extension_safety_fails() -> None:
    gating = _build_monitor_policy_aware_gating(
        policy_interpretation={
            "policy_available": True,
            "entry_style": "breakout",
            "relaxable_checks": ["reclaim_gate_ok"],
        },
        signal_evidence={
            "checks": {
                "reclaim_gate_ok": False,
                "breakout_path_ok": True,
                "confidence_ok": True,
                "volume_ok": True,
            },
            "derived": {
                "reclaim_distance_to_ready": -0.0004,
                "too_extended": True,
            },
        },
        policy_alignment_summary={
            "alignment_state": "partial",
            "top_failed_required_checks": [],
        },
        legacy_triggered=False,
        legacy_reason="below_vwap_reclaim_not_ready",
    )

    assert gating.get("available") is True
    assert gating.get("applied") is False
    assert gating.get("relaxations_applied") == []
    assert "safe_relaxation_conditions_not_met" in list(gating.get("notes") or [])


def test_intraday_entry_scoring_shadow_mode_records_score_but_preserves_decision(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_SCORING_ENABLED", "false")
    monkeypatch.setenv("MONITOR_SCORING_SHADOW_MODE", "true")
    monkeypatch.setenv("MONITOR_ENTRY_SCORE_THRESHOLD", "8")

    out = evaluate_intraday_entry_signal(_rows_breakout())

    assert out["triggered"] is True
    assert out["decision"] == "BUY"
    assert out["scoring_mode"] == "shadow"
    assert out["legacy_entry_decision"] == "BUY"
    assert out["scoring_entry_decision"] == "WAIT"
    assert out["score_passed"] is False
    assert isinstance(out.get("score_breakdown"), dict)
    assert isinstance(out.get("signal_evidence"), dict)
    assert isinstance((out.get("signal_evidence") or {}).get("scores"), dict)


def test_intraday_entry_scoring_enabled_allows_entry_when_threshold_met(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_SCORING_ENABLED", "true")
    monkeypatch.setenv("MONITOR_SCORING_SHADOW_MODE", "false")
    monkeypatch.setenv("MONITOR_ENTRY_SCORE_THRESHOLD", "3")

    out = evaluate_intraday_entry_signal(_rows_breakout())

    assert out["scoring_mode"] == "enabled"
    assert out["hard_filter_passed"] is True
    assert out["score_passed"] is True
    assert out["scoring_entry_decision"] == "BUY"
    assert out["triggered"] is True
    assert out["decision"] == "BUY"
    assert (out.get("signal_evidence") or {}).get("derived", {}).get("weighted_score_passed") is True


def test_intraday_entry_scoring_enabled_no_longer_blocks_legacy_buy_when_threshold_not_met(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_SCORING_ENABLED", "true")
    monkeypatch.setenv("MONITOR_SCORING_SHADOW_MODE", "false")
    monkeypatch.setenv("MONITOR_ENTRY_SCORE_THRESHOLD", "8")

    out = evaluate_intraday_entry_signal(_rows_breakout())

    assert out["legacy_entry_decision"] == "BUY"
    assert out["scoring_entry_decision"] == "WAIT"
    assert out["score_passed"] is False
    assert out["triggered"] is True
    assert out["decision"] == "BUY"
    assert out["reason"] != "monitor_score_threshold_not_met"
    assert (out.get("signal_evidence") or {}).get("derived", {}).get("weighted_score_passed") is False


def test_intraday_entry_scoring_enabled_does_not_force_wait_into_buy_even_if_score_threshold_is_met(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_SCORING_ENABLED", "true")
    monkeypatch.setenv("MONITOR_SCORING_SHADOW_MODE", "false")
    monkeypatch.setenv("MONITOR_ENTRY_SCORE_THRESHOLD", "1")

    rows = _rows_pullback_rebound()
    rows[-1]["close"] = 100.1
    rows[-1]["high"] = 100.4
    rows[-1]["vwap"] = 100.8

    out = evaluate_intraday_entry_signal(rows, frame={"playbook": "pullback"})

    assert out["legacy_entry_decision"] == "WAIT"
    assert out["scoring_entry_decision"] == "BUY"
    assert out["score_passed"] is True
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
    assert out["reason"] == "below_vwap_reclaim_not_ready"
    assert (out.get("signal_evidence") or {}).get("derived", {}).get("weighted_score_passed") is True


def test_intraday_entry_scoring_hard_filter_blocks_without_data(monkeypatch) -> None:
    monkeypatch.setenv("MONITOR_SCORING_ENABLED", "true")
    monkeypatch.setenv("MONITOR_SCORING_SHADOW_MODE", "false")
    monkeypatch.setenv("MONITOR_ENTRY_SCORE_THRESHOLD", "3")

    out = evaluate_intraday_entry_signal([])

    assert out["hard_filter_passed"] is False
    assert "minute_candle_missing" in list(out.get("hard_filter_fail_reasons") or [])
    assert out["score_passed"] is False
    assert out["triggered"] is False
    assert out["decision"] == "WAIT"
