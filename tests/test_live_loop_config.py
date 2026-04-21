from libs.runtime.live_loop_config import build_live_loop_initial_state, session_hard_gate_enabled


def test_build_live_loop_initial_state_integrated_chain_enables_auto_skill_runner() -> None:
    state = build_live_loop_initial_state("005930", tick_pipeline="integrated_chain")
    assert state["symbol"] == "005930"
    assert state["m13_tick_pipeline"] == "integrated_chain"
    assert state["auto_skill_runner"] is True
    assert state["use_exit_policy"] is True


def test_build_live_loop_initial_state_normalizes_unknown_pipeline() -> None:
    state = build_live_loop_initial_state("005930", tick_pipeline="unknown")
    assert state["m13_tick_pipeline"] == "legacy_m10"


def test_session_hard_gate_enabled_defaults_true(monkeypatch) -> None:
    monkeypatch.delenv("M31_MOCK_EXAM_SESSION_HARD_GATE", raising=False)
    assert session_hard_gate_enabled(session_hard_gate_flag=False, allow_offhours_flag=False) is True


def test_session_hard_gate_enabled_can_be_disabled_for_offhours(monkeypatch) -> None:
    monkeypatch.setenv("M31_MOCK_EXAM_SESSION_HARD_GATE", "true")
    assert session_hard_gate_enabled(session_hard_gate_flag=False, allow_offhours_flag=True) is False
