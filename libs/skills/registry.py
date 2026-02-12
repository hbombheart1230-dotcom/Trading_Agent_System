from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml


@dataclass(frozen=True)
class SkillStep:
    api_id: str
    defaults: Dict[str, Any]
    map: Dict[str, Any]


@dataclass(frozen=True)
class SkillSpec:
    skill: str
    description: str
    outputs: str
    steps: List[SkillStep]


class SkillRegistry:
    """Loads Composite Skill specs from config/skills/*.yaml.

    Supports BOTH:
      - verbose (defaults/map)
      - minimal (step is string api_id, optional map only)
    """

    def __init__(self, skills_dir: str | Path = "config/skills"):
        self.skills_dir = Path(skills_dir)
        self._specs: Dict[str, SkillSpec] = {}

    def load(self) -> "SkillRegistry":
        self._specs.clear()
        if not self.skills_dir.exists():
            return self
        for p in sorted(self.skills_dir.glob("*.yaml")):
            data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            spec = self._parse(data)
            self._specs[spec.skill] = spec
        return self

    def get(self, skill: str) -> SkillSpec:
        if skill not in self._specs:
            raise KeyError(f"Unknown skill: {skill}")
        return self._specs[skill]

    def list_skills(self) -> List[str]:
        return sorted(self._specs.keys())

    def _parse(self, data: Dict[str, Any]) -> SkillSpec:
        skill = str(data.get("skill") or "").strip()
        if not skill:
            raise ValueError("SkillSpec missing 'skill'")
        desc = str(data.get("description") or "").strip()
        outputs = str(data.get("outputs") or "").strip() or "RawDTO"

        steps_raw = data.get("steps") or []
        if not isinstance(steps_raw, list) or not steps_raw:
            raise ValueError(f"SkillSpec '{skill}' missing steps")

        steps: List[SkillStep] = []
        for s in steps_raw:
            if isinstance(s, str):
                steps.append(SkillStep(api_id=s.strip(), defaults={}, map={}))
                continue
            if not isinstance(s, dict):
                continue
            api_id = str(s.get("api_id") or "").strip()
            if not api_id:
                raise ValueError(f"SkillSpec '{skill}' step missing api_id")
            defaults = s.get("defaults") or {}
            mapping = s.get("map") or {}
            steps.append(SkillStep(api_id=api_id, defaults=dict(defaults), map=dict(mapping)))

        return SkillSpec(skill=skill, description=desc, outputs=outputs, steps=steps)
