import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import { AppShell } from "./AppShell";
import type { RunSession } from "@/types/pdca";
import { ScrollArea } from "@/components/ui/scroll-area";

interface Props {
  run: RunSession;
  title?: string;
  subtitle?: React.ReactNode;
  actions?: React.ReactNode;
  children: React.ReactNode;
}

export function PageShell({ run, title, subtitle, actions, children }: Props) {
  return (
    <AppShell
      sidebar={<Sidebar awsStatus={run.awsEnvironment.status} awsAccountMask={run.awsEnvironment.accountMask} />}
      topBar={<TopBar run={run} />}
    >
      <ScrollArea className="h-full scrollbar-thin">
        <div className="mx-auto max-w-7xl px-4 py-6 md:px-6 md:py-8">
          {(title || actions) && (
            <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
              <div>
                {title && <h1 className="font-display text-2xl font-bold tracking-tight md:text-3xl">{title}</h1>}
                {subtitle && <p className="mt-1 text-sm text-text-secondary">{subtitle}</p>}
              </div>
              {actions && <div className="flex items-center gap-2">{actions}</div>}
            </header>
          )}
          {children}
        </div>
      </ScrollArea>
    </AppShell>
  );
}
