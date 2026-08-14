import {
  Activity,
  BarChart3,
  BellRing,
  Binoculars,
  ChartNoAxesCombined,
  ClipboardList,
  FileText,
  Gauge,
  MessagesSquare,
  ShieldCheck,
} from "lucide-react";

export const NAV_ITEMS = [
  { id: "overview", label: "운영 요약", icon: Gauge, public: true },
  { id: "performance", label: "성과", icon: ChartNoAxesCombined, public: true },
  { id: "trades", label: "거래", icon: ClipboardList, public: true },
  { id: "opportunities", label: "기회", icon: Binoculars, public: true },
  { id: "strategies", label: "전략", icon: BarChart3, public: true },
  { id: "market", label: "시장", icon: Activity, public: true },
  { id: "alerts", label: "운영 알림", icon: BellRing, public: true },
  { id: "llm-operations", label: "LLM 운영", icon: MessagesSquare, public: false },
  { id: "reports", label: "리포트", icon: FileText, public: false },
  { id: "data-quality", label: "데이터 품질", icon: ShieldCheck, public: false },
] as const;

export type PageId = (typeof NAV_ITEMS)[number]["id"];

export function pageFromHash(): PageId {
  const value = window.location.hash.replace(/^#\/?/, "") as PageId;
  return NAV_ITEMS.some((item) => item.id === value) ? value : "overview";
}
