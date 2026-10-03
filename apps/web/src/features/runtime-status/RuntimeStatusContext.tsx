import { createContext, useContext, useEffect, type ReactNode } from "react";

import { useApi, type ApiState } from "../../shared/api/useApi";
import type { RuntimeStatus } from "./types";

const RuntimeStatusContext = createContext<ApiState<RuntimeStatus> | null>(null);

export function RuntimeStatusProvider({ children }: { children: ReactNode }) {
  const state = useApi<RuntimeStatus>("/api/v1/runtime/status");

  useEffect(() => {
    const timer = window.setInterval(state.refresh, 15_000);
    return () => window.clearInterval(timer);
  }, [state.refresh]);

  return <RuntimeStatusContext.Provider value={state}>{children}</RuntimeStatusContext.Provider>;
}

export function useRuntimeStatus(): ApiState<RuntimeStatus> {
  const state = useContext(RuntimeStatusContext);
  if (!state) throw new Error("useRuntimeStatus must be used inside RuntimeStatusProvider");
  return state;
}
