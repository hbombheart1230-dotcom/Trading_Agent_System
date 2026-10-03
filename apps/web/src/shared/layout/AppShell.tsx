import { Menu, RefreshCw, ShieldCheck, X } from "lucide-react";
import { useState, type ReactNode } from "react";

import { NAV_ITEMS, type PageId } from "../../app/navigation";
import { RuntimeStateBadge } from "../../features/runtime-status/RuntimeStateBadge";
import { useRuntimeStatus } from "../../features/runtime-status/RuntimeStatusContext";
import { useApi } from "../api/useApi";
import { formatDateTime } from "../formatters/dates";
import { StatusPill } from "../components/StatusPill";

interface Health {
  status: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | "STALE" | "NO_DATA" | "ERROR";
  checked_at: string;
  read_only: boolean;
  execution_callable: boolean;
  exposure_profile: "private" | "public";
  public_mode: boolean;
}

interface Props {
  page: PageId;
  onNavigate: (page: PageId) => void;
  children: ReactNode;
}

export function AppShell({ page, onNavigate, children }: Props) {
  const [menuOpen, setMenuOpen] = useState(false);
  const health = useApi<Health>("/health/ready");
  const runtime = useRuntimeStatus();
  const navigate = (target: PageId) => {
    onNavigate(target);
    setMenuOpen(false);
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand-block">
          <div className="brand-mark">TA</div>
          <div><strong>Trading Agent</strong><span>Operations Console</span></div>
          <button className="mobile-close" onClick={() => setMenuOpen(false)} title="메뉴 닫기"><X size={20} /></button>
        </div>
        <nav className="primary-nav" aria-label="주요 화면">
          {NAV_ITEMS.filter((item) => !health.data?.public_mode || item.public).map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.id} className={page === item.id ? "active" : ""} onClick={() => navigate(item.id)}>
                <Icon size={18} /><span>{item.label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-safety">
          <ShieldCheck size={17} />
          <div><strong>READ ONLY</strong><span>주문 실행 경로 없음</span></div>
        </div>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <button className="mobile-menu" onClick={() => setMenuOpen(true)} title="메뉴 열기"><Menu size={20} /></button>
          <div className="topbar-signals">
            <span className="readonly-flag">READ ONLY</span>
            <span className="mode-flag">SIMULATION / MOCK</span>
            {runtime.data && <RuntimeStateBadge state={runtime.data.runtime_state} />}
            {health.data?.public_mode && <span className="public-flag">PUBLIC SHOWCASE</span>}
            {health.data && <StatusPill status={health.data.status} />}
          </div>
          <div className="topbar-meta">
            <span>Execution callable: <strong>NO</strong></span>
            <span>API {health.data ? formatDateTime(health.data.checked_at) : "확인 중"}</span>
            <button className="icon-button" onClick={health.refresh} title="API 상태 갱신"><RefreshCw size={17} /></button>
          </div>
        </header>
        <main className="content">{children}</main>
      </div>
      {menuOpen && <button className="sidebar-scrim" aria-label="메뉴 닫기" onClick={() => setMenuOpen(false)} />}
    </div>
  );
}
