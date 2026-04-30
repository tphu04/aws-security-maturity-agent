import type { ReactNode } from "react";

interface Props {
  sidebar: ReactNode;
  topBar: ReactNode;
  children: ReactNode;
  rightPanel?: ReactNode; // optional, only shown on workspace
  inputBar?: ReactNode;   // optional bottom bar
}

export function AppShell({ sidebar, topBar, children, rightPanel, inputBar }: Props) {
  return (
    <div className="relative flex h-screen min-h-0 w-full overflow-hidden bg-background">
      <div className="pointer-events-none absolute inset-0 grid-bg opacity-30" />
      {sidebar}
      <div className="relative flex min-w-0 flex-1 flex-col">
        {topBar}
        <div className="relative flex min-h-0 flex-1">
          <div className="flex min-w-0 flex-1 flex-col">
            <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
            {inputBar}
          </div>
          {rightPanel && (
            <aside className="hidden w-trace-panel-width shrink-0 border-l border-border/60 bg-bg-surface/50 backdrop-blur-md lg:block">
              {rightPanel}
            </aside>
          )}
        </div>
      </div>
    </div>
  );
}
