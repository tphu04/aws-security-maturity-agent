import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { QaLine, UserLine } from "../types";

export function UserMessage({ line }: { line: UserLine }) {
  return (
    <div className="flex justify-end my-3 animate-fadeUp">
      <div className="max-w-[80%] bg-userBubble text-white rounded-2xl rounded-br-md px-4 py-2.5 shadow-soft whitespace-pre-wrap break-words">
        {line.text}
      </div>
    </div>
  );
}

export function AssistantMessage({ line }: { line: QaLine }) {
  const empty = !line.markdown;
  return (
    <div className="flex gap-3 my-3 animate-fadeUp">
      <div className="shrink-0 w-7 h-7 rounded-lg bg-brand text-white grid place-items-center text-xs font-bold mt-1">P</div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-dim mb-0.5">PDCA Agent</div>
        <div className="bg-elevated border border-border rounded-2xl rounded-tl-md px-4 py-3 shadow-soft">
          <div className={"md " + (!line.done && empty ? "text-dim italic" : "")}>
            {empty && !line.done ? (
              <span className="cursor">đang suy nghĩ</span>
            ) : (
              <>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{line.markdown}</ReactMarkdown>
                {!line.done && <span className="cursor" />}
              </>
            )}
          </div>
          {(line.intent?.reason || line.sources?.length) && line.done && (
            <div className="mt-3 pt-2 border-t border-border flex flex-wrap gap-3 text-xs">
              {line.intent && (
                <details className="text-dim">
                  <summary className="hover:text-fg">
                    <span className="chev">▸</span> intent={line.intent.intent} · {line.intent.confidence.toFixed(2)}
                  </summary>
                  {line.intent.reason && <div className="mt-1 pl-4">{line.intent.reason}</div>}
                </details>
              )}
              {line.sources && line.sources.length > 0 && (
                <details className="text-dim">
                  <summary className="hover:text-fg">
                    <span className="chev">▸</span> sources ({line.sources.length})
                  </summary>
                  <ul className="mt-1 pl-4 space-y-1 list-none">
                    {line.sources.map((s, i) => (
                      <li key={s.checkId || s.url || i}>
                        {s.url ? (
                          <a href={s.url} target="_blank" rel="noreferrer" className="text-info hover:underline">
                            {s.title || s.checkId || s.url}
                          </a>
                        ) : (
                          <span className="text-fg">{s.title || s.checkId}</span>
                        )}
                        {s.snippet && <div className="text-dim pl-3 mt-0.5">{s.snippet}</div>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
