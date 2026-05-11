import type { ReactNode } from "react";

interface Props {
  sidebar: ReactNode;
  topBar: ReactNode;
  children: ReactNode;
  inputBar?: ReactNode;
}

export function AppShell({ sidebar, topBar, children, inputBar }: Props) {
  return (
    <div className="relative flex h-screen min-h-0 w-full overflow-hidden bg-background">
      {sidebar}
      <div className="relative flex min-w-0 flex-1 flex-col">
        {topBar}
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
        {inputBar}
      </div>
    </div>
  );
}
