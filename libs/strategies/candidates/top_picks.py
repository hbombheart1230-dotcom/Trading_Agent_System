from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from libs.core.settings import Settings
from libs.read.kiwoom_condition_reader import ConditionQuery, KiwoomConditionReader
from libs.read.kiwoom_rank_reader import KiwoomRankReader, RankMode
from .base import Candidate, CandidateGenerator


def _fallback_candidates() -> List[Candidate]:
    # Reasonable default set (KRX 대표주 + 대형주). Always 3~5.
    syms = ["005930", "000660", "035420", "051910", "068270"]
    return [Candidate(symbol=s, why="fallback_universe") for s in syms[:5]]


def _ensure_unique(symbols: List[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for s in symbols:
        if isinstance(s, str) and s.strip() and s not in seen:
            out.append(s.strip())
            seen.add(s)
    return out


@dataclass(frozen=True)
class TopPicksCandidateGenerator(CandidateGenerator):
    """Candidate generator: market rank (거래대금/거래량 등) + condition filter.

    - Rank list: default 거래대금 상위 Top-N
    - If condition results are available, filter rank list by them.
    - Always returns 3~5 candidates (fallback on failures).

    Test/DRY_RUN injection points:
      - state['candidate_symbols'] = [...]  (highest priority)
      - state['mock_rank_symbols'] = [...]  (rank list)
      - state['mock_condition_symbols'] = [...]  (condition filter)
    """

    topk: int = 5
    rank_topn: int = 30
    rank_mode: RankMode = RankMode.VALUE
    condition: Optional[ConditionQuery] = None

    def generate(self, state: Dict[str, Any]) -> List[Candidate]:
        injected = state.get("candidate_symbols")
        if isinstance(injected, list) and all(isinstance(x, str) for x in injected) and injected:
            syms = _ensure_unique(injected)[: self.topk]
            return [Candidate(symbol=s, why="state.candidate_symbols") for s in syms]

        # 1) Rank list
        rank_syms: List[str] = []
        mocked_rank = state.get("mock_rank_symbols")
        if isinstance(mocked_rank, list) and mocked_rank:
            rank_syms = _ensure_unique([str(x) for x in mocked_rank])
        else:
            try:
                s = Settings.from_env()
                if os.getenv("DRY_RUN", "").strip().lower() in ("1", "true", "yes"):
                    raise RuntimeError("DRY_RUN")
                if not (s.kiwoom_app_key and s.kiwoom_app_secret):
                    raise RuntimeError("missing_credentials")
                reader = KiwoomRankReader.from_env()
                rank_syms = _ensure_unique(
                    reader.get_top_symbols(mode=self.rank_mode, topk=int(self.rank_topn))
                )
            except Exception:
                rank_syms = []

        # 2) Optional condition filter
        cond_reader = KiwoomConditionReader()
        cond_syms = _ensure_unique(cond_reader.get_symbols(state, query=self.condition, limit=500))
        if cond_syms:
            cond_set = set(cond_syms)
            rank_syms = [s for s in rank_syms if s in cond_set]

        if not rank_syms:
            return _fallback_candidates()

        top = rank_syms[: self.topk]
        why = f"top_picks:{self.rank_mode.value}"
        if cond_syms:
            why += "+condition"
        return [Candidate(symbol=s, why=why) for s in top]
