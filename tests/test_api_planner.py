from libs.catalog.api_planner import ApiPlanner
from libs.catalog.api_discovery import ApiMatch
from libs.catalog.api_catalog import ApiSpec


def make_match(api_id: str, score: float):
    return ApiMatch(
        spec=ApiSpec(api_id=api_id),
        score=score,
        reasons=[]
    )


def test_planner_select_high_confidence():
    planner = ApiPlanner(select_threshold=0.8, margin_threshold=0.1)
    matches = [
        make_match("A", 0.9),
        make_match("B", 0.7),
    ]
    result = planner.plan(matches)
    assert result.action == "select"
    assert result.selected.spec.api_id == "A"


def test_planner_ask_on_ambiguous():
    planner = ApiPlanner(select_threshold=0.9, margin_threshold=0.2)
    matches = [
        make_match("A", 0.85),
        make_match("B", 0.8),
    ]
    result = planner.plan(matches)
    assert result.action == "ask"