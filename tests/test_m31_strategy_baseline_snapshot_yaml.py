from pathlib import Path


def test_exam_strategy_baseline_yaml_exists_and_has_primary_strategy():
    path = Path("configs/exam_strategy_baseline.yaml")
    assert path.exists()
    body = path.read_text(encoding="utf-8")
    assert "schema_version: strategy_v1_exam_baseline.v1" in body
    assert "name: regime_momentum_v1" in body
    assert "runtime_profile: staging" in body
    assert "kiwoom_mode: mock" in body
    assert "approval_mode: manual" in body
