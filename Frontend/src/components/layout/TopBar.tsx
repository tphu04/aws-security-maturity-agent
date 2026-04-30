import { Menu, PanelRightOpen, Download, Settings, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { AwsStatusPill, RunStatusPill, NodeStatusPill, Code, Pill } from "@/components/ui/status-pill";
import { useRouter } from "@/state/router";
import type { RunSession } from "@/types/pdca";

interface Props {
  run: RunSession;
  onOpenTrace?: () => void;
  onOpenNav?: () => void;
}

export function TopBar({ run, onOpenTrace, onOpenNav }: Props) {
  const { go } = useRouter();
  const currentNode = run.graphNodes.find((n) => n.name === run.currentNode);

  return (
    <header className="relative z-20 flex h-14 items-center justify-between gap-2 border-b border-border/60 bg-bg-base/70 px-3 backdrop-blur-md md:px-5">
      <div className="flex min-w-0 items-center gap-2 md:gap-3">
        <Button variant="ghost" size="icon" className="md:hidden" onClick={onOpenNav}>
          <Menu className="h-5 w-5" />
        </Button>
        <div className="hidden items-center gap-2 md:flex">
          <ShieldCheck className="h-4 w-4 text-primary" />
          <span className="font-display text-sm font-semibold tracking-tight">PDCA Prowler Agent</span>
        </div>
        <div className="hidden h-6 w-px bg-border md:block" />
        <div className="hidden min-w-0 items-center gap-2 md:flex">
          <span className="text-[10px] uppercase tracking-wider text-text-muted">run</span>
          <Code className="truncate">{run.id}</Code>
        </div>
      </div>

      <div className="flex items-center gap-2 overflow-x-auto scrollbar-thin">
        <AwsStatusPill status={run.awsEnvironment.status} />
        <Pill tone="neutral" className="hidden md:inline-flex">
          <span className="text-text-muted">node</span>
          <Code className="ml-1 px-1 py-0">{run.currentNode}</Code>
        </Pill>
        {currentNode && <NodeStatusPill status={currentNode.status} />}
        <RunStatusPill status={run.status} />
        <span className="hidden sm:inline-flex">
          <Pill tone="neutral">
            <span className="text-text-muted">report</span>
            <span className="ml-1 capitalize text-text-primary">{run.report.status}</span>
          </Pill>
        </span>
      </div>

      <div className="flex items-center gap-1.5">
        <Button variant="outline" size="sm" className="hidden lg:inline-flex" onClick={() => go("report")}>
          <Download className="h-4 w-4" /> Export
        </Button>
        <Button variant="ghost" size="icon" className="hidden md:inline-flex" onClick={() => go("settings")}>
          <Settings className="h-4 w-4" />
        </Button>
        <Button variant="outline" size="sm" className="lg:hidden" onClick={onOpenTrace}>
          <PanelRightOpen className="h-4 w-4" /> Trace
        </Button>
      </div>
    </header>
  );
}
