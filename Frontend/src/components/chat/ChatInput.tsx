import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, ArrowUp, RefreshCw, Square } from "lucide-react";
import { useRun } from "@/state/run";
import { cn } from "@/lib/utils";

const DEFAULT_PROMPTS: PromptChip[] = [
  { label: "S3 public access là gì?", kind: "qa",   payload: "What is S3 public access?" },
  { label: "IAM risks phổ biến",      kind: "qa",   payload: "What are common IAM risks?" },
  { label: "Scan S3",                 kind: "scan", payload: "scan s3" },
  { label: "Scan IAM",                kind: "scan", payload: "scan iam" },
];

export interface PromptChip {
  label: string;
  kind: "qa" | "scan";
  payload: string;
}

interface Props {
  onSend: (text: string) => void;
  onStop?: () => void;
  pending?: boolean;
  canStop?: boolean;
  stopping?: boolean;
  suggestions?: PromptChip[];
}

export function ChatInput({ onSend, onStop, pending, canStop, stopping, suggestions }: Props) {
  const prompts = suggestions && suggestions.length ? suggestions : DEFAULT_PROMPTS;
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const { chatbotOnline, refreshEnvironment, refreshScannerHealth } = useRun();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [value]);

  const submit = () => {
    const v = value.trim();
    if (!v || pending || canStop) return;
    onSend(v);
    setValue("");
  };

  const handleAction = () => {
    if (canStop) {
      onStop?.();
      return;
    }
    submit();
  };

  return (
    <div className="bg-background/80 backdrop-blur-md">
      <div className="mx-auto max-w-3xl px-4 pb-4 pt-2">
        {/* Prompt chips */}
        <div className="mb-2 flex flex-wrap gap-1.5">
          {prompts.slice(0, 4).map((p) => (
            <button
              key={p.label}
              type="button"
              onClick={() => onSend(p.payload)}
              disabled={pending || canStop}
              className={cn(
                "inline-flex h-7 items-center gap-1.5 rounded-full px-3 text-[11.5px] transition-colors disabled:opacity-40",
                "border bg-transparent",
                p.kind === "scan"
                  ? "border-border/70 text-text-secondary hover:border-primary/50 hover:text-primary hover:bg-primary/5"
                  : "border-border/70 text-text-secondary hover:border-brand-violet/50 hover:text-brand-violet hover:bg-brand-violet/5"
              )}
            >
              {p.label}
            </button>
          ))}
        </div>

        {/* Input box */}
        <div className={cn(
          "relative rounded-2xl border bg-card/80 shadow-sm transition-all",
          "focus-within:border-primary/50 focus-within:shadow-[0_0_0_3px_hsl(var(--primary)/0.12)]",
          "border-border/60",
        )}>
          <Textarea
            ref={ref}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
            }}
            placeholder="Hỏi về AWS security hoặc yêu cầu quét…"
            aria-label="Chat message"
            className="min-h-[52px] resize-none bg-transparent px-4 py-3.5 pr-14 text-sm placeholder:text-text-muted/60 focus:outline-none border-0 shadow-none"
            disabled={pending}
          />
          <Button
            onClick={handleAction}
            disabled={canStop ? stopping : pending || !value.trim()}
            size="icon"
            aria-label={canStop ? "Stop current scan" : "Send message"}
            title={canStop ? "Stop current scan" : "Send message"}
            className={cn(
              "absolute bottom-2.5 right-2.5 h-8 w-8 rounded-xl disabled:opacity-30",
              canStop && "bg-status-error text-white hover:bg-status-error/90",
            )}
          >
            {canStop
              ? (stopping ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-3.5 w-3.5 fill-current" />)
              : pending
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <ArrowUp className="h-4 w-4" />}
          </Button>
        </div>

        {/* Status bar */}
        <div className="mt-1.5 flex items-center justify-between px-1 text-[10px] text-text-muted">
          <span>
            <kbd className="rounded border border-border bg-bg-elevated/60 px-1 font-mono">Enter</kbd> to send ·{" "}
            <kbd className="rounded border border-border bg-bg-elevated/60 px-1 font-mono">Shift+Enter</kbd> newline
          </span>
          <span className="inline-flex items-center gap-1.5">
            {chatbotOnline === null
              ? <><Loader2 className="h-3 w-3 animate-spin" /> connecting…</>
              : chatbotOnline
                ? <span className="text-status-success">● connected</span>
                : <>
                    <span className="text-status-warning">● offline</span>
                    <button
                      type="button"
                      onClick={() => { void refreshEnvironment(); void refreshScannerHealth(); }}
                      className="inline-flex items-center gap-0.5 rounded border border-border/60 bg-bg-elevated/40 px-1.5 py-0.5 hover:text-text-primary hover:border-primary/40"
                    >
                      <RefreshCw className="h-2.5 w-2.5" /> retry
                    </button>
                  </>}
          </span>
        </div>
      </div>
    </div>
  );
}
