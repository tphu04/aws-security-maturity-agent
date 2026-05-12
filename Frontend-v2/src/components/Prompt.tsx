import { useEffect, useRef } from "react";

interface Props {
  value: string;
  busy: boolean;
  pendingApproval: boolean;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onHistoryPrev: () => void;
  onHistoryNext: () => void;
  onShortcut: (k: "a" | "r" | "d" | "s") => void;
}

export function Prompt({
  value, busy, pendingApproval, onChange, onSubmit, onHistoryPrev, onHistoryNext, onShortcut,
}: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    ref.current?.focus();
  }, []);

  // Auto-resize textarea up to 6 rows
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 6 * 20) + "px";
  }, [value]);

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
      return;
    }
    if (e.key === "ArrowUp" && (value === "" || ref.current?.selectionStart === 0)) {
      e.preventDefault();
      onHistoryPrev();
      return;
    }
    if (e.key === "ArrowDown" && (value === "" || ref.current?.selectionStart === value.length)) {
      e.preventDefault();
      onHistoryNext();
      return;
    }
    // Approval shortcuts: only when input is empty AND there is a pending approval
    if (pendingApproval && value === "") {
      if (e.key === "a") { e.preventDefault(); onShortcut("a"); return; }
      if (e.key === "r") { e.preventDefault(); onShortcut("r"); return; }
      if (e.key === "s") { e.preventDefault(); onShortcut("s"); return; }
      if (e.key === "d") { e.preventDefault(); onShortcut("d"); return; }
    }
  }

  return (
    <div className="border-t border-border bg-panel px-3 py-2 flex items-start gap-2">
      <span className={busy ? "text-warn" : "text-accent"}>{busy ? "…" : ">"}</span>
      <textarea
        ref={ref}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        rows={1}
        placeholder={
          pendingApproval
            ? "type your reply, or press a/r/d/s for approval…"
            : busy
            ? "streaming…"
            : "hỏi bất cứ điều gì, hoặc 'quét s3'…"
        }
        className="flex-1 bg-transparent resize-none outline-none placeholder:text-dim"
        disabled={false}
      />
    </div>
  );
}
