import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type Selection = {
  evidenceId?: string;
  findingId?: string;
  messageId?: string;
  taskId?: string;
};

type Ctx = {
  selection: Selection;
  selectEvidence: (id?: string, related?: { findingId?: string; messageId?: string }) => void;
  selectFinding: (id?: string) => void;
  selectTask: (id?: string) => void;
  clear: () => void;
};

const SelectionContext = createContext<Ctx | null>(null);

export function SelectionProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<Selection>({});
  const value = useMemo<Ctx>(
    () => ({
      selection,
      selectEvidence: (id, r) =>
        setSelection({ evidenceId: id, findingId: r?.findingId, messageId: r?.messageId }),
      selectFinding: (id) => setSelection({ findingId: id }),
      selectTask: (id) => setSelection({ taskId: id }),
      clear: () => setSelection({}),
    }),
    [selection]
  );
  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}

export function useSelection() {
  const ctx = useContext(SelectionContext);
  if (!ctx) throw new Error("useSelection must be used inside SelectionProvider");
  return ctx;
}
