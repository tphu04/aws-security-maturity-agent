import { useState } from "react";
import { loadEndpoints, saveEndpoints } from "../api";

interface Props { onClose: () => void }

export function Settings({ onClose }: Props) {
  const cur = loadEndpoints();
  const [chatbot, setChatbot] = useState(cur.chatbot);
  const [scanner, setScanner] = useState(cur.scanner);
  const [rag, setRag]         = useState(cur.rag);

  function save() {
    saveEndpoints({ chatbot, scanner, rag });
    onClose();
    if (confirm("Lưu thành công. Tải lại trang để áp dụng endpoint mới?")) {
      location.reload();
    }
  }

  return (
    <div
      className="fixed inset-0 bg-black/30 flex items-center justify-center z-50 px-4"
      onClick={onClose}
    >
      <div
        className="bg-panel rounded-2xl shadow-card border border-border p-6 w-[520px] max-w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="font-semibold text-lg">Endpoints</div>
          <button onClick={onClose} className="text-dim hover:text-fg text-xl leading-none">×</button>
        </div>
        <Row label="Chatbot API" value={chatbot} onChange={setChatbot} placeholder="/api/chatbot" />
        <Row label="Scanner API" value={scanner} onChange={setScanner} placeholder="/api/scanner" />
        <Row label="RAG API"     value={rag}     onChange={setRag}     placeholder="/api/rag" />
        <div className="text-xs text-dim mt-3">
          Mặc định đi qua Vite dev proxy. Bản production đặt
          <code className="mx-1 px-1 bg-elevated rounded">VITE_CHATBOT_API_URL</code> v.v.
        </div>
        <div className="mt-6 flex justify-end gap-2">
          <button onClick={onClose} className="px-4 py-2 rounded-lg border border-border hover:bg-elevated text-sm">Huỷ</button>
          <button onClick={save} className="px-4 py-2 rounded-lg bg-brand text-white text-sm hover:opacity-90 shadow-soft">Lưu & tải lại</button>
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, onChange, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  return (
    <div className="my-3">
      <div className="text-xs text-dim mb-1 font-medium">{label}</div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-bg border border-border rounded-lg px-3 py-2 outline-none focus:border-borderStrong"
      />
    </div>
  );
}
