import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { QaLine } from "../types";

export function Bubble({ line }: { line: QaLine }) {
  return (
    <div className="my-1">
      <div className="flex items-start gap-2">
        <span className="text-info">⬢</span>
        <div className="flex-1 min-w-0">
          <div className="md text-fg">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {line.markdown || (line.done ? "" : "…")}
            </ReactMarkdown>
          </div>
          {line.intent?.reason && (
            <details className="mt-1 text-dim text-[12px]">
              <summary>
                <span className="chev">▸</span> intent={line.intent.intent} ·
                conf {line.intent.confidence.toFixed(2)}
              </summary>
              <div className="pl-4 mt-1">{line.intent.reason}</div>
            </details>
          )}
          {line.sources && line.sources.length > 0 && (
            <details className="mt-1 text-dim text-[12px]">
              <summary><span className="chev">▸</span> sources ({line.sources.length})</summary>
              <ul className="pl-4 mt-1 list-none">
                {line.sources.map((s, i) => (
                  <li key={i} className="my-0.5">
                    {s.url ? (
                      <a href={s.url} target="_blank" rel="noreferrer" className="text-info">
                        {s.title || s.checkId || s.url}
                      </a>
                    ) : (
                      <span>{s.title || s.checkId || "(source)"}</span>
                    )}
                    {s.snippet && <div className="text-dim pl-3">{s.snippet}</div>}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
