import { AlertTriangle, Database, LoaderCircle, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

interface Props {
  loading: boolean;
  error: string | null;
  empty?: boolean;
  emptyText?: string;
  onRetry?: () => void;
  children: ReactNode;
}

export function DataState({ loading, error, empty, emptyText, onRetry, children }: Props) {
  if (loading) {
    return <div className="data-state"><LoaderCircle className="spin" size={22} />데이터를 읽는 중입니다.</div>;
  }
  if (error) {
    return (
      <div className="data-state data-state-error">
        <AlertTriangle size={22} />
        <span>{error}</span>
        {onRetry && <button className="icon-button" onClick={onRetry} title="다시 불러오기"><RefreshCw size={17} /></button>}
      </div>
    );
  }
  if (empty) {
    return <div className="data-state"><Database size={22} />{emptyText ?? "선택한 범위에 데이터가 없습니다."}</div>;
  }
  return children;
}
