import type { AwsEnvironment } from "../types";
import type { ConnStatus } from "../reducer";

interface Props {
  env: AwsEnvironment | null;
  conn: ConnStatus;
  sidebarOpen: boolean;
  onToggleSidebar: () => void;
}

export function Header({ env, conn, sidebarOpen, onToggleSidebar }: Props) {
  const dot =
    conn === "connected" ? "bg-accent" :
    conn === "offline"   ? "bg-err"    : "bg-warn";

  return (
    <header className="h-14 border-b border-border px-4 flex items-center gap-3 bg-panel">
      {!sidebarOpen && (
        <button
          onClick={onToggleSidebar}
          className="p-2 rounded-lg hover:bg-elevated text-dim"
          title="Show sidebar"
        >›</button>
      )}
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-lg bg-brand text-white grid place-items-center font-bold text-sm">P</div>
        <div className="leading-tight">
          <div className="font-semibold text-sm">PDCA Prowler</div>
          <div className="text-[11px] text-dim flex items-center gap-1.5">
            <span className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`} />
            {conn === "connected"
              ? <>{env?.accountMask ?? "—"} · {env?.region ?? "—"}</>
              : conn}
          </div>
        </div>
      </div>
      <div className="ml-auto text-xs text-dim">
        {env?.ragAvailable !== undefined && (
          <span className={env.ragAvailable ? "text-accent" : "text-dim"}>
            RAG {env.ragAvailable ? "on" : "off"}
          </span>
        )}
      </div>
    </header>
  );
}
