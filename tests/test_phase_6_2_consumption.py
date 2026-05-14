import os
import pytest
from graphs.nodes.strategist_node import _load_deterministic_read_models
from libs.reporting.trade_report_ai import build_ai_trade_report

def test_strategist_deterministic_input_structure(tmp_path):
    # 1. Strategist가 오직 Read Model Fact에만 의존하는지 검증
    state = {
        "reports_root": str(tmp_path)
    }
    candidates = ["AAPL", "MSFT"]
    
    # Execute
    facts = _load_deterministic_read_models(state, candidates)
    
    # Assert
    assert "recent_trades" in facts
    assert "daily_summary" in facts
    assert "symbol_patterns" in facts
    assert isinstance(facts["recent_trades"], list)
    assert isinstance(facts["symbol_patterns"], dict)
    # Default code constraints without Envs
    assert len(facts["symbol_patterns"]) <= 5 

def test_report_consumption_enforces_fact_narrative_split(monkeypatch):
    # 2. 모든 리포트 생성 경로가 Fact/Narrative로 강제 통일되었는지 검증 (LLM Off 상태)
    monkeypatch.setenv("DRY_RUN", "1")
    
    story_input = {
        "trade_id": "TRD_999",
        "symbol": "NVDA",
        "action": "BUY",
        "status": "closed"
    }
    
    # Execute
    report = build_ai_trade_report(story_input)
    
    # Assert strict structure
    assert "fact_payload" in report
    assert "narrative" in report
    
    # Assert Deterministic Facts are present
    assert report["fact_payload"]["trade"]["trade_id"] == "TRD_999"
    assert report["fact_payload"]["trade"]["symbol"] == "NVDA"
    
    # Assert LLM Narrative is safely skipped/empty
    assert report["narrative"]["status"] == "skipped"
    assert report["narrative"]["source"] == "llm"
    assert report["narrative"]["based_on"] == "fact_payload"
