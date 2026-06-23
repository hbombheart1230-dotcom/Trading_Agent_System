from libs.reporting.q8_lane_decision_table import _verdict


def test_q8_lane_decision_table_blocks_verdict_when_trust_gate_blocks() -> None:
    row = {
        "name": "opening_momentum",
        "candidate_count": 100,
        "observed_count": 100,
        "coverage": 1.0,
        "avg_return_5m_pct": 1.2,
        "avg_return_15m_pct": 1.4,
        "avg_mfe_5m_pct": 2.0,
        "avg_mae_5m_pct": -0.3,
    }

    verdict = _verdict(row, promotion_allowed=False)

    assert verdict["verdict"] == "TRUST_GATE_BLOCKED"
    assert verdict["decision"] == "retain under observation"


def test_q8_lane_decision_table_allows_missed_opportunity_after_trust_gate() -> None:
    row = {
        "name": "opening_momentum",
        "candidate_count": 100,
        "observed_count": 100,
        "coverage": 1.0,
        "avg_return_5m_pct": 1.2,
        "avg_return_15m_pct": 1.4,
        "avg_mfe_5m_pct": 2.0,
        "avg_mae_5m_pct": -0.3,
    }

    verdict = _verdict(row, promotion_allowed=True)

    assert verdict["verdict"] == "MISSED_OPPORTUNITY"
    assert verdict["decision"] == "relaxation candidate"
