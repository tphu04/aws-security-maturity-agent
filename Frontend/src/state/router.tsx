import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type ViewName =
  | "landing"
  | "workspace"
  | "settings"
  | "results"
  | "report"
  | "history"
  | "run_detail"
  | "verification"
  | "approvals";

type Ctx = {
  view: ViewName;
  go: (v: ViewName) => void;
};

const RouterContext = createContext<Ctx | null>(null);

export function RouterProvider({ initial = "landing", children }: { initial?: ViewName; children: ReactNode }) {
  const [view, setView] = useState<ViewName>(initial);
  const go = useCallback((v: ViewName) => setView(v), []);
  const value = useMemo(() => ({ view, go }), [view, go]);
  return <RouterContext.Provider value={value}>{children}</RouterContext.Provider>;
}

export function useRouter() {
  const ctx = useContext(RouterContext);
  if (!ctx) throw new Error("useRouter must be used inside RouterProvider");
  return ctx;
}
