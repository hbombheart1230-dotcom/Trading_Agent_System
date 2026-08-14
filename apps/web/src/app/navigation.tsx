import {
  Activity,
  BarChart3,
  Binoculars,
  ChartNoAxesCombined,
  ClipboardList,
  FileText,
  Gauge,
  ShieldCheck,
} from "lucide-react";

export const NAV_ITEMS = [
  { id: "overview", label: "운영 요약", icon: Gauge },
  { id: "performance", label: "성과", icon: ChartNoAxesCombined },
  { id: "trades", label: "거래", icon: ClipboardList },
  { id: "opportunities", label: "기회", icon: Binoculars },
  { id: "strategies", label: "전략", icon: BarChart3 },
  { id: "market", label: "시장", icon: Activity },
  { id: "reports", label: "리포트", icon: FileText },
  { id: "data-quality", label: "데이터 품질", icon: ShieldCheck },
] as const;

export type PageId = (typeof NAV_ITEMS)[number]["id"];

export function pageFromHash(): PageId {
  const value = window.location.hash.replace(/^#\/?/, "") as PageId;
  return NAV_ITEMS.some((item) => item.id === value) ? value : "overview";
}
