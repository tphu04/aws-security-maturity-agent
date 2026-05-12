interface Props { done: number; total: number; width?: number }

export function ProgressBar({ done, total, width = 120 }: Props) {
  const safeTotal = Math.max(total, 1);
  const pct = Math.min(100, Math.round((done / safeTotal) * 100));
  return (
    <span className="inline-flex items-center gap-2 align-middle">
      <span
        className="inline-block bg-border rounded-full overflow-hidden"
        style={{ width, height: 6 }}
      >
        <span
          className="block bg-info h-full transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </span>
      <span className="text-dim text-xs">{done}/{total || done} · {pct}%</span>
    </span>
  );
}
