import { useState } from "react";
import type { ApprovalLine, Severity } from "../types";

interface Props {
  line: ApprovalLine;
  onDecide: (taskId: string, decision: "approved" | "rejected" | "skipped") => void;
}

const sevColor: Record<Severity, string> = {
  critical: "bg-err text-white",
  high:     "bg-err text-white",
  medium:   "bg-warn text-white",
  low:      "bg-info text-white",
  info:     "bg-muted text-white",
};

const sevLabel: Record<Severity, string> = {
  critical: "Nghiêm trọng",
  high:     "Cao",
  medium:   "Trung bình",
  low:      "Thấp",
  info:     "Thông tin",
};

const effortLabel: Record<string, string> = {
  low:    "Đơn giản",
  medium: "Trung bình",
  high:   "Phức tạp",
};

const stepTypeLabel: Record<string, string> = {
  cli:     "AWS CLI",
  iac:     "IaC",
  console: "Console",
  other:   "",
};

export function ApprovalCard({ line, onDecide }: Props) {
  const [showDetails, setShowDetails] = useState(false);
  const t = line.task;
  const resolved = line.resolved;
  const isManual = t.decision === "manual_required" || t.manualOnly;

  const permissionOk = t.requiredAwsPermission && t.requiredAwsPermission !== "see tool docstring";
  const impactText = t.expectedImpact
    || (t.proposedAction ? t.proposedAction.split(".")[0] + "." : "");

  return (
    <div data-approval={t.id} className="flex gap-3 my-4 animate-fadeUp">
      <div className={`shrink-0 w-7 h-7 rounded-lg border grid place-items-center mt-1 text-sm ${isManual ? "bg-infoSoft text-info border-info/30" : "bg-warnSoft text-warn border-warn/30"}`}>
        {isManual ? "✎" : "⚠"}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-dim mb-0.5">{isManual ? "Cần xử lý thủ công" : "Cần phê duyệt"}</div>
        <div className="bg-panel border border-warn/40 rounded-2xl rounded-tl-md p-4 shadow-card">

          {/* Header */}
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <div className="font-semibold">{t.toolName}</div>
            <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${sevColor[t.severity] || "bg-muted text-white"}`}>
              {sevLabel[t.severity] || t.severity}
            </span>
            <span className="text-dim text-xs">· {t.findingTitle}</span>
          </div>

          {/* Key info grid */}
          <div className="grid grid-cols-[90px_1fr] gap-x-3 gap-y-1 text-sm">
            <div className="text-dim">Tài nguyên</div>
            <div className="font-mono text-[13px] break-all">{t.resource}</div>
            <div className="text-dim">Tác động</div>
            <div>{impactText || <span className="text-dim italic">Không có thông tin</span>}</div>
          </div>

          {/* AI reasoning */}
          {t.proposedAction && (
            <div className="mt-3 border-l-2 border-info/40 pl-3 text-sm">
              <div className="text-xs text-info font-medium mb-1 flex items-center gap-1">
                <span>⬢</span> Lý do AI chọn hành động này
              </div>
              <div className="text-fg/80 leading-relaxed">{t.proposedAction}</div>
            </div>
          )}

          {/* Manual guidance — high-level Vietnamese overview from planner LLM */}
          {t.manualGuidance ? (
            <div className="mt-3 border-l-2 border-warn/40 pl-3 text-sm">
              <div className="text-xs text-warn font-medium mb-1">⚠ Lưu ý thực hiện thủ công</div>
              <div className="text-fg/80 leading-relaxed">{t.manualGuidance}</div>
            </div>
          ) : null}

          {/* RAG steps — technical reference (collapsed by default) */}
          {(t.ragSteps?.length || t.ragEffort || t.ragRollback) ? (
            <details className="mt-3 text-sm">
              <summary className="text-dim hover:text-fg cursor-pointer">
                <span className="chev">▸</span> Tài liệu kỹ thuật tham khảo
                {t.ragEffort && (
                  <span className="ml-1">· Độ phức tạp: {effortLabel[t.ragEffort] || t.ragEffort}</span>
                )}
              </summary>
              <div className="mt-2 pl-4 space-y-2 text-[13px]">
                {t.ragSteps && t.ragSteps.length > 0 && (
                  <ol className="list-decimal pl-4 space-y-1">
                    {t.ragSteps.map((s, idx) => {
                      const typeStr = stepTypeLabel[s.type] ?? "";
                      return (
                        <li key={`${t.id}-step-${idx}`}>
                          {typeStr && <span className="text-dim text-xs">[{typeStr}]</span>}{" "}
                          <code className="bg-elevated px-1.5 py-0.5 rounded">{s.snippet}</code>
                          {s.prerequisite && (
                            <div className="text-dim text-xs pl-2 mt-0.5">Yêu cầu trước: {s.prerequisite}</div>
                          )}
                        </li>
                      );
                    })}
                  </ol>
                )}
                {t.ragRollback && (
                  <div>Hoàn tác: <code className="bg-elevated px-1.5 py-0.5 rounded">{t.ragRollback}</code></div>
                )}
                {t.ragSideEffects && t.ragSideEffects.length > 0 && (
                  <div className="text-dim">Tác dụng phụ: {t.ragSideEffects.join(", ")}</div>
                )}
              </div>
            </details>
          ) : null}

          {/* Technical details (collapsed) */}
          <details
            open={showDetails}
            onToggle={(e) => setShowDetails((e.target as HTMLDetailsElement).open)}
            className="mt-2 text-sm"
          >
            <summary className="text-dim hover:text-fg cursor-pointer">
              <span className="chev">▸</span> Tham số kỹ thuật
            </summary>
            <div className="mt-2 pl-4 space-y-1 text-[13px]">
              {permissionOk && (
                <div>Quyền IAM: <code className="bg-elevated px-1.5 py-0.5 rounded">{t.requiredAwsPermission}</code></div>
              )}
              <pre className="!my-1 !bg-elevated !border-border">{JSON.stringify(t.toolParams, null, 2)}</pre>
              {t.guardChecks && (
                <div className="text-dim text-xs">
                  {t.guardChecks.registeredTool && t.guardChecks.isRemediationCategory
                    ? t.guardChecks.notManualOnly
                      ? <span className="text-accent">✓ Có thể tự động thực thi</span>
                      : <span className="text-info">Chỉ thực hiện thủ công</span>
                    : <span className="text-warn">⚠ Tool chưa được đăng ký</span>
                  }
                </div>
              )}
            </div>
          </details>

          {/* Action buttons */}
          <div className="mt-4 flex items-center gap-2 flex-wrap">
            {resolved ? (
              <div className={
                "px-3 py-1.5 rounded-full text-sm font-medium " +
                (resolved === "approved" ? "bg-accentSoft text-accent" :
                 resolved === "rejected" ? "bg-errSoft text-err" :
                                            "bg-elevated text-dim")
              }>
                {resolved === "approved" ? "✓ Đã phê duyệt" :
                 resolved === "rejected" ? "✗ Đã từ chối" :
                                            "↷ Đã ghi nhận"}
              </div>
            ) : isManual ? (
              <>
                <div className="flex-1 text-xs text-dim bg-infoSoft rounded-lg px-3 py-2">
                  Task này chỉ thực hiện được thủ công (không có tool tự động). Làm theo hướng dẫn bên trên, sau đó nhấn <strong>Xác nhận</strong>.
                </div>
                <button
                  onClick={() => onDecide(t.id, "skipped")}
                  className="px-4 py-1.5 rounded-full bg-info text-white text-sm font-medium hover:opacity-90 transition shadow-soft"
                >Xác nhận</button>
                <button
                  onClick={() => setShowDetails(v => !v)}
                  className="px-4 py-1.5 rounded-full bg-panel text-fg border border-border text-sm hover:bg-elevated transition"
                >{showDetails ? "Ẩn" : "Chi tiết"}</button>
              </>
            ) : (
              <>
                <button
                  onClick={() => onDecide(t.id, "approved")}
                  className="px-4 py-1.5 rounded-full bg-accent text-white text-sm font-medium hover:opacity-90 transition shadow-soft"
                >Phê duyệt</button>
                <button
                  onClick={() => onDecide(t.id, "rejected")}
                  className="px-4 py-1.5 rounded-full bg-panel text-err border border-err/40 text-sm font-medium hover:bg-errSoft transition"
                >Từ chối</button>
                <button
                  onClick={() => onDecide(t.id, "skipped")}
                  className="px-4 py-1.5 rounded-full bg-panel text-dim border border-border text-sm hover:bg-elevated transition"
                >Bỏ qua</button>
                <button
                  onClick={() => setShowDetails(v => !v)}
                  className="px-4 py-1.5 rounded-full bg-panel text-fg border border-border text-sm hover:bg-elevated transition ml-auto"
                >{showDetails ? "Ẩn" : "Chi tiết"}</button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
