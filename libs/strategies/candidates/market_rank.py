from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from libs.core.settings import Settings
from libs.read.kiwoom_rank_reader import KiwoomRankReader, RankMode
from .base import Candidate, CandidateGenerator


def _fallback_candidates() -> List[Candidate]:
    # Reasonable default set (KRX 대표주 + 대형주). Always 3~5.
    syms = ["005930", "000660", "035420", "051910", "068270"]
    return [Candidate(symbol=s, why="fallback_universe") for s in syms[:5]]


@dataclass(frozen=True)
class MarketRankCandidateGenerator(CandidateGenerator):
    """Candidate generator using Kiwoom 'rank' APIs (거래량/거래대금/등락률 상위 등).

    - Tries real API (via token) when credentials are available.
    - Falls back to a small built-in universe if API is unavailable.
    """

    mode: RankMode = RankMode.VOLUME
    topk: int = 5

    def generate(self, state: Dict[str, Any]) -> List[Candidate]:
        # Allow explicit injection for tests / experiments
        injected = state.get("candidate_symbols")
        if isinstance(injected, list) and all(isinstance(x, str) for x in injected) and injected:
            return [Candidate(symbol=s, why="state.candidate_symbols") for s in injected[: self.topk]]

        # If running in environments without credentials, do not hard-fail.
        try:
            s = Settings.from_env()
            # Respect explicit DRY_RUN hints
            if os.getenv("DRY_RUN", "").strip().lower() in ("1", "true", "yes"):
                raise RuntimeError("DRY_RUN")
            if not (s.kiwoom_app_key and s.kiwoom_app_secret):
                raise RuntimeError("missing_credentials")

            reader = KiwoomRankReader.from_env()
            symbols = reader.get_top_symbols(mode=self.mode, topk=int(self.topk))
            symbols = [x for x in symbols if isinstance(x, str) and x.strip()]
            if symbols:
                return [Candidate(symbol=sym, why=f"market_rank:{self.mode.value}") for sym in symbols[: self.topk]]
        except Exception:
            pass

        return _fallback_candidates()
