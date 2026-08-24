from __future__ import annotations

from collections import defaultdict
from typing import Any, Mapping, Sequence

from .contracts import HORIZONS
from .metrics import feature_outcome, performance


def _dedupe_feature_episodes(
    episodes: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    for row in episodes:
        strategy = dict(row.get("strategy", {}))
        if strategy.get("canonical_evidence_status") != "OBSERVED":
            continue
        identity = dict(row.get("identity", {}))
        key = (str(identity.get("day") or ""), str(identity.get("symbol") or ""))
        if key not in result:
            result[key] = row
    return list(result.values())


def build_strategist_stage2_review(
    feature_episodes: Sequence[Mapping[str, Any]],
    agent_scorecard: Mapping[str, Any],
) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for row in _dedupe_feature_episodes(feature_episodes):
        observation = dict(row.get("strategy_choice_observation", {}))
        playbook = dict(observation.get("playbook_choice", {}))
        tactic = dict(observation.get("tactic_choice", {}))
        generation = dict(observation.get("generation", {}))
        groups[("changed_from_pre_llm", str(playbook.get("changed_from_pre_llm")))].append(row)
        groups[("default_tactic", str(tactic.get("selected_is_playbook_default")))].append(row)
        groups[("generation_mode", str(generation.get("mode") or "MISSING"))].append(row)
    observational = []
    for (dimension, value), rows in sorted(groups.items()):
        observational.append(
            {
                "dimension": dimension,
                "value": value,
                "episode_count": len(rows),
                "horizons": {
                    horizon: performance([feature_outcome(row, horizon) for row in rows])
                    for horizon in HORIZONS
                },
            }
        )
    components = dict(agent_scorecard.get("components", {}))
    strategist = dict(components.get("strategist", {}))
    return {
        "official_scorecard_range": dict(agent_scorecard.get("range", {})),
        "official_ranking_overlay": dict(strategist.get("ranking_overlay", {})),
        "official_post_scanner_refresh": dict(
            strategist.get("post_scanner_refresh", {})
        ),
        "observational_splits": observational,
        "authority_change_applied": False,
        "behavior_change_authorized": False,
        "interpretation_boundary": (
            "Generation-mode and tactic-choice splits are confounded observations. "
            "They do not estimate a causal LLM effect."
        ),
    }
