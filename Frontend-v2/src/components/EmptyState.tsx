interface Props {
  onPick: (prompt: string) => void;
}

const suggestions: Array<{ label: string; sub: string; payload: string; icon: string }> = [
  { label: "Quét S3",         sub: "scan toàn bộ checks dịch vụ S3",    payload: "quét s3",                   icon: "🪣" },
  { label: "Kiểm tra IAM",    sub: "rủi ro IAM users, policies",        payload: "quét iam",                  icon: "🔐" },
  { label: "BPA là gì?",      sub: "giải thích S3 Block Public Access", payload: "S3 Block Public Access là gì?", icon: "📖" },
  { label: "Đề xuất khắc phục", sub: "công cụ nào tự động được",        payload: "những finding nào có thể tự động khắc phục?", icon: "🛠" },
];

export function EmptyState({ onPick }: Props) {
  return (
    <div className="mx-auto max-w-3xl px-4 py-12 animate-fadeUp">
      <div className="text-center mb-8">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-brand text-white text-2xl font-bold shadow-card mb-3">P</div>
        <h1 className="text-2xl font-semibold">PDCA Prowler</h1>
        <p className="text-dim mt-1">Trợ lý kiểm thử & khắc phục bảo mật AWS theo chu trình PDCA.</p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {suggestions.map((s) => (
          <button
            key={s.payload}
            onClick={() => onPick(s.payload)}
            className="text-left p-4 rounded-xl bg-panel border border-border hover:border-borderStrong hover:shadow-soft transition flex items-start gap-3"
          >
            <span className="text-xl">{s.icon}</span>
            <div className="min-w-0">
              <div className="font-medium">{s.label}</div>
              <div className="text-xs text-dim mt-0.5">{s.sub}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
