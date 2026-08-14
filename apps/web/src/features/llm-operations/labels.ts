const STAGES: Record<string, string> = {
  market_frame: "1차 시장 프레임",
  market_strategy_frame: "1차 시장 프레임",
  strategic_frame: "전략 프레임",
  selected_symbol_tactical_refresh: "2차 종목 전술 갱신",
  position_management: "3차 보유 관리",
  overnight_decision: "4차 오버나이트",
  trade_report_generation: "거래 리포트 생성",
  trade_report: "거래 리포트·요약",
  operator_ui: "장중 운영 브리프",
};

const ISSUES: Record<string, string> = {
  RECENT_EVENT_WINDOW_ONLY: "지연시간은 대용량 이벤트 로그의 최근 bounded 구간만 집계합니다.",
  TOKEN_USAGE_NOT_RECORDED: "OpenRouter 토큰과 비용 정보가 호출 아티팩트에 저장되지 않습니다.",
  EVENT_LOG_UNAVAILABLE: "최근 호출 지연시간 이벤트 로그를 찾지 못했습니다.",
  EVENT_LOG_TAIL_UNREADABLE: "최근 호출 지연시간 구간을 읽지 못했습니다.",
};

export function stageLabel(value: string): string {
  return STAGES[value] ?? value.replaceAll("_", " ");
}

export function issueLabel(value: string): string {
  if (value.startsWith("TRADE_REPORT_ROUTE_MISMATCH")) {
    return "거래 리포트의 실제 생성 경로는 MiniMax지만 generic router에는 Nemotron free가 남아 있습니다.";
  }
  return ISSUES[value] ?? value.replaceAll("_", " ");
}

export function roleStateLabel(value: string): string {
  return ({ ACTIVE: "사용 중", DEGRADED: "오류 있음", CONFIGURED: "설정됨", ROUTING_WARNING: "경로 불일치" } as Record<string, string>)[value] ?? value;
}
