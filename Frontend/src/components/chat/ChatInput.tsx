import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Sparkles, Loader2 } from "lucide-react";

const PROMPTS = [
  "Scan S3",
  "Check IAM risks",
  "Scan EC2",
  "Generate report",
  "Explain failed checks",
  "Verify remediation",
];

interface Props {
  onSend: (text: string) => void;
  pending?: boolean;
}

export function ChatInput({ onSend, pending }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 180) + "px";
  }, [value]);

  const submit = () => {
    const v = value.trim();
    if (!v || pending) return;
    onSend(v);
    setValue("");
  };

  return (
    <div className="border-t border-border/60 bg-bg-base/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-4xl flex-col gap-2 px-4 py-3 md:px-6">
        <div className="flex flex-wrap gap-1.5">
          {PROMPTS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setValue((v) => (v ? v + " " : "") + p)}
              className="group inline-flex items-center gap-1.5 rounded-full border border-border/70 bg-bg-elevated/40 px-2.5 py-1 text-[11px] text-text-secondary transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-text-primary"
            >
              <Sparkles className="h-3 w-3 text-primary/70 group-hover:text-primary" />
              {p}
            </button>
          ))}
        </div>

        <div className="group flex items-end gap-2 rounded-xl border border-border bg-card/60 p-1.5 ring-1 ring-transparent transition-all focus-within:border-primary/50 focus-within:ring-primary/30">
          <Textarea
            ref={ref}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
            }}
            placeholder="Ask the agent to scan AWS services…"
            className="min-h-[44px] flex-1 bg-transparent"
            disabled={pending}
          />
          <Button onClick={submit} disabled={pending || !value.trim()} size="icon" className="h-9 w-9">
            {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>

        <div className="flex items-center justify-between text-[10px] text-text-muted">
          <span>
            Press <kbd className="rounded border border-border bg-bg-elevated/60 px-1 font-mono">Enter</kbd> to send ·{" "}
            <kbd className="rounded border border-border bg-bg-elevated/60 px-1 font-mono">Shift</kbd> +{" "}
            <kbd className="rounded border border-border bg-bg-elevated/60 px-1 font-mono">Enter</kbd> for newline
          </span>
          <span className="font-mono">mock-session · no backend</span>
        </div>
      </div>
    </div>
  );
}
