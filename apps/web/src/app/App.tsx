import { lazy, Suspense, useEffect, useState, type ComponentType } from "react";

import { RuntimeStatusProvider } from "../features/runtime-status/RuntimeStatusContext";
import { AppShell } from "../shared/layout/AppShell";
import { pageFromHash, type PageId } from "./navigation";

const OverviewPage = lazy(() => import("../features/overview/OverviewPage").then((module) => ({ default: module.OverviewPage })));
const OperationsPage = lazy(() => import("../features/operations/OperationsPage").then((module) => ({ default: module.OperationsPage })));
const PerformancePage = lazy(() => import("../features/performance/PerformancePage").then((module) => ({ default: module.PerformancePage })));
const TradesPage = lazy(() => import("../features/trades/TradesPage").then((module) => ({ default: module.TradesPage })));
const OpportunitiesPage = lazy(() => import("../features/opportunities/OpportunitiesPage").then((module) => ({ default: module.OpportunitiesPage })));
const StrategiesPage = lazy(() => import("../features/strategies/StrategiesPage").then((module) => ({ default: module.StrategiesPage })));
const MarketPage = lazy(() => import("../features/market/MarketPage").then((module) => ({ default: module.MarketPage })));
const LlmOperationsPage = lazy(() => import("../features/llm-operations/LlmOperationsPage").then((module) => ({ default: module.LlmOperationsPage })));
const AlertsPage = lazy(() => import("../features/alerts/AlertsPage").then((module) => ({ default: module.AlertsPage })));
const PatchNotesPage = lazy(() => import("../features/patch-notes/PatchNotesPage").then((module) => ({ default: module.PatchNotesPage })));
const ReportsPage = lazy(() => import("../features/reports/ReportsPage").then((module) => ({ default: module.ReportsPage })));
const DataQualityPage = lazy(() => import("../features/data-quality/DataQualityPage").then((module) => ({ default: module.DataQualityPage })));

const PAGES: Record<PageId, ComponentType> = {
  overview: OverviewPage,
  operations: OperationsPage,
  performance: PerformancePage,
  trades: TradesPage,
  opportunities: OpportunitiesPage,
  strategies: StrategiesPage,
  market: MarketPage,
  alerts: AlertsPage,
  "patch-notes": PatchNotesPage,
  "llm-operations": LlmOperationsPage,
  reports: ReportsPage,
  "data-quality": DataQualityPage,
};

export function App() {
  const [page, setPage] = useState<PageId>(pageFromHash);
  useEffect(() => {
    const handleHash = () => setPage(pageFromHash());
    window.addEventListener("hashchange", handleHash);
    return () => window.removeEventListener("hashchange", handleHash);
  }, []);
  const navigate = (target: PageId) => {
    window.location.hash = target;
    setPage(target);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const Page = PAGES[page];
  return (
    <RuntimeStatusProvider>
      <AppShell page={page} onNavigate={navigate}>
        <Suspense fallback={<div className="data-state">화면을 불러오는 중입니다.</div>}>
          <Page />
        </Suspense>
      </AppShell>
    </RuntimeStatusProvider>
  );
}
