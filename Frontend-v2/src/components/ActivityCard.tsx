import type { EventLine, ExecLine } from "../types";
import { ProgressBar } from "./ProgressBar";

type ActivityLine = EventLine | ExecLine;

const toneClass = (tone?: string) =>
  tone === "ok"   ? "text-accent" :
  tone === "warn" ? "text-warn"   :
  tone === "err"  ? "text-err"    :
  tone === "info" ? "text-info"   : "text-fg";

interface Props {
  lines: ActivityLine[];
}

/**
 * Renders a contiguous block of event/exec lines as a single card —
 * makes the run trace feel like one activity stream rather than chat noise.
 */
export function ActivityCard({ lines }: Props) {
  if (lines.length === 0) return null;
  return (
    <div className="flex gap-3 my-3 animate-fadeUp">
      <div className="shrink-0 w-7 h-7 rounded-lg bg-elevated border border-border text-dim grid place-items-center text-xs mt-1">▸</div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-dim mb-0.5">Agent activity</div>
        <div className="bg-panel border border-border rounded-2xl rounded-tl-md p-3 shadow-soft mono">
          {lines.map(l => (
            <Row key={l.id} line={l} />
          ))}
        </div>
      </div>
    </div>
  );
}

function Row({ line }: { line: ActivityLine }) {
  if (line.k === "exec") {
    return (
      <div className="flex items-start gap-2 py-0.5">
        <span className={line.ok ? "text-accent" : "text-err"}>{line.ok ? "✓" : "✗"}</span>
        <span className={line.ok ? "text-fg" : "text-err"}>{line.text}</span>
      </div>
    );
  }
  const ev = line as EventLine;
  const isPhaseHeader = ev.icon === "▶";
  return (
    <div className={isPhaseHeader ? "py-1 mt-1 border-t border-border/60 first:border-0" : "py-0.5"}>
      <div className="flex items-start gap-2">
        <span className={toneClass(ev.tone)}>{ev.icon}</span>
        <div className="flex-1 min-w-0">
          <span className={`${toneClass(ev.tone)} ${isPhaseHeader ? "font-medium" : ""}`}>{ev.text}</span>
          {ev.progress && (
            <span className="ml-2"><ProgressBar done={ev.progress.done} total={ev.progress.total} /></span>
          )}
          {ev.reasoning && (
            <details className="text-dim text-[12px]">
              <summary className="hover:text-fg"><span className="chev">▸</span> why</summary>
              <div className="pl-4 mt-1 whitespace-pre-wrap font-sans">{ev.reasoning}</div>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
