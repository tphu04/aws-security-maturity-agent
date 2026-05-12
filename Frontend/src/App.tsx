import { TooltipProvider } from "@/components/ui/tooltip";
import { SelectionProvider } from "@/state/selection";
import { RouterProvider, useRouter } from "@/state/router";
import { RunProvider, useRun } from "@/state/run";

import { LandingView } from "@/views/LandingView";
import { WorkspaceView } from "@/views/WorkspaceView";
import { SettingsView } from "@/views/SettingsView";
import { ResultsView } from "@/views/ResultsView";
import { ReportView } from "@/views/ReportView";
import { HistoryView } from "@/views/HistoryView";
import { RunDetailView } from "@/views/RunDetailView";
import { VerificationView } from "@/views/VerificationView";
import { ApprovalsView } from "@/views/ApprovalsView";
import { FloatingToggles } from "@/components/floating-toggles";

function Router() {
  const { view } = useRouter();
  const { run, setRun, approveTask, rejectTask, skipTask } = useRun();

  // Mount the prefs effects on every view (mutation observer for VI
  // translation must keep running) but hide its UI everywhere — Settings has
  // its own inline copy.
  const showFloating = false;

  const content = (() => {
    switch (view) {
      case "landing":      return <LandingView />;
      case "workspace":    return <WorkspaceView run={run} setRun={setRun} />;
      case "settings":     return <SettingsView run={run} />;
      case "results":      return <ResultsView run={run} />;
      case "report":       return <ReportView run={run} />;
      case "history":      return <HistoryView run={run} />;
      case "run_detail":   return <RunDetailView run={run} />;
      case "verification": return <VerificationView run={run} />;
      case "approvals":    return <ApprovalsView run={run} onApprove={approveTask} onReject={rejectTask} onSkip={skipTask} />;
      default:             return <LandingView />;
    }
  })();

  return (
    <>
      {content}
      <FloatingToggles visible={showFloating} />
    </>
  );
}

export default function App() {
  return (
    <TooltipProvider delayDuration={150}>
      <SelectionProvider>
        <RunProvider>
          <RouterProvider initial="landing">
            <Router />
          </RouterProvider>
        </RunProvider>
      </SelectionProvider>
    </TooltipProvider>
  );
}
