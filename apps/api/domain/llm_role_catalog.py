from __future__ import annotations

ROLE_CATALOG = (
    {
        "role": "strategist",
        "label": "전략가",
        "configured_model": "deepseek/deepseek-v3.2",
        "fallback_model": "minimax/minimax-m2.5",
        "configuration_source": "strategist balanced policy",
    },
    {
        "role": "trade_report",
        "label": "거래 리포트·요약",
        "configured_model": "nvidia/nemotron-3-ultra-550b-a55b:free",
        "fallback_model": None,
        "configuration_source": "live report generation path",
    },
    {
        "role": "operator_ui",
        "label": "장중 운영 브리프",
        "configured_model": "minimax/minimax-m2.5",
        "fallback_model": None,
        "configuration_source": "operator UI route",
    },
    {
        "role": "reporter_intraday",
        "label": "장중 리포터",
        "configured_model": "minimax/minimax-m2.5",
        "fallback_model": None,
        "configuration_source": "intraday reporter route",
    },
    {
        "role": "reporter_final",
        "label": "장후 최종 리뷰",
        "configured_model": "moonshotai/kimi-k2.5",
        "fallback_model": None,
        "configuration_source": "final reporter route",
    },
    {
        "role": "daily_report",
        "label": "일일 LLM 요약",
        "configured_model": "moonshotai/kimi-k2.5",
        "fallback_model": None,
        "configuration_source": "daily report route",
    },
)

ROUTING_ISSUES: tuple[str, ...] = ()
