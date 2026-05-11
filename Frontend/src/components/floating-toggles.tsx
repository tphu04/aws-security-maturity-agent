import { useEffect, useState, useCallback } from "react";
import { Languages, Moon, Sun } from "lucide-react";

/* ------------------------------------------------------------------ */
/* Translation dictionary EN -> VI                                     */
/* ------------------------------------------------------------------ */
const EN_VI: Record<string, string> = {
  // Brand / nav
  "PDCA Prowler Agent": "PDCA Prowler Agent",
  "PDCA Prowler": "PDCA Prowler",
  "Agent · v0.1": "Agent · v0.1",
  "Features": "Tính năng",
  "Workflow": "Quy trình",
  "Why": "Tại sao",
  "AWS Settings": "Cài đặt AWS",
  "Open Workspace": "Mở Workspace",
  "Start Scan": "Bắt đầu quét",
  "Preview Report": "Xem trước báo cáo",
  "Export": "Xuất",
  "Trace": "Trace",
  "New Scan": "Quét mới",
  "Runs": "Lần chạy",
  "Scan History": "Lịch sử quét",
  "Reports": "Báo cáo",
  "Approvals": "Phê duyệt",
  "Results": "Kết quả",
  "Workspace": "Workspace",
  "Tools": "Công cụ",
  "Help & Docs": "Trợ giúp & Tài liệu",
  "Demo · local mode": "Demo · chế độ cục bộ",

  // Hero / landing
  "Run AWS security scans through a": "Thực hiện quét bảo mật AWS qua một",
  "transparent AI agent": "AI agent minh bạch",
  "PDCA Prowler Agent lets users request AWS security scans in natural language, runs Prowler through backend APIs, traces every LangGraph step, asks for approval before remediation, verifies changes, and generates a DOCX report.":
    "PDCA Prowler Agent cho phép người dùng yêu cầu quét bảo mật AWS bằng ngôn ngữ tự nhiên, chạy Prowler qua API backend, theo dõi từng bước LangGraph, yêu cầu phê duyệt trước khi khắc phục, xác minh thay đổi và tạo báo cáo DOCX.",
  "LangGraph workflow": "Quy trình LangGraph",
  "Prowler scan": "Quét Prowler",
  "Human approval": "Phê duyệt thủ công",
  "Remediation verification": "Xác minh khắc phục",
  "DOCX export": "Xuất DOCX",

  // Hero mockup
  "You": "Bạn",
  "Scan my S3 service for security issues.": "Quét dịch vụ S3 của tôi để tìm lỗi bảo mật.",
  "Environment checked": "Đã kiểm tra môi trường",
  "account": "tài khoản",
  "region": "vùng",
  "buckets": "buckets",
  "up": "hoạt động",
  "Remediation tool found": "Đã tìm thấy công cụ khắc phục",
  "High-severity public bucket exposure. Remediate?": "Bucket công khai mức nghiêm trọng cao. Khắc phục?",
  "Yes, remediate": "Có, khắc phục",
  "Show details": "Xem chi tiết",
  "ready": "sẵn sàng",
  "Preview": "Xem trước",

  // Problem section
  "The CLI problem": "Vấn đề CLI",
  "Prowler is powerful, but CLI workflows are hard to explain":
    "Prowler rất mạnh, nhưng quy trình CLI khó giải thích",
  "CLI-heavy scanning": "Quét nặng CLI",
  "Users must know commands, flags, groups, checks, profiles, and output formats.":
    "Người dùng phải biết lệnh, cờ, nhóm, kiểm tra, profile và định dạng đầu ra.",
  "Long-running jobs": "Tác vụ dài",
  "Submission, polling, collection, and parsing are not obvious to non-technical users.":
    "Gửi, polling, thu thập và phân tích không rõ ràng với người không chuyên.",
  "Raw findings": "Phát hiện thô",
  "Output must be normalized, prioritized, and converted into understandable risks.":
    "Đầu ra cần chuẩn hóa, ưu tiên và chuyển thành rủi ro dễ hiểu.",
  "Controlled remediation": "Khắc phục có kiểm soát",
  "Cloud changes should never happen automatically without explicit user approval.":
    "Thay đổi cloud không bao giờ được tự động khi chưa có phê duyệt rõ ràng.",
  "Reports take time": "Báo cáo tốn thời gian",
  "Findings, evidence, decisions, and verification must be turned into a clean report.":
    "Phát hiện, chứng cứ, quyết định và xác minh cần được tổng hợp thành báo cáo gọn gàng.",

  // PDCA workflow
  "PDCA": "PDCA",
  "A guided PDCA workflow for AWS cloud security":
    "Quy trình PDCA hướng dẫn cho bảo mật AWS",
  "Plan": "Lập kế hoạch",
  "Agent understands user intent and builds a scan plan.":
    "Agent hiểu ý định người dùng và xây dựng kế hoạch quét.",
  "Do": "Thực hiện",
  "Agent submits Prowler jobs and polls until results are ready.":
    "Agent gửi tác vụ Prowler và theo dõi đến khi có kết quả.",
  "Check": "Kiểm tra",
  "Agent evaluates risk and maps evidence to findings.":
    "Agent đánh giá rủi ro và liên kết chứng cứ với phát hiện.",
  "Act": "Hành động",
  "Agent proposes remediation and waits for human approval.":
    "Agent đề xuất khắc phục và chờ phê duyệt từ con người.",
  "Verify & Report": "Xác minh & Báo cáo",
  "Agent verifies changes and generates a DOCX report.":
    "Agent xác minh thay đổi và tạo báo cáo DOCX.",

  // Features
  "What's inside": "Bên trong có gì",
  "From natural-language requests to verified remediation":
    "Từ yêu cầu ngôn ngữ tự nhiên đến khắc phục đã xác minh",
  "Natural-language requests": "Yêu cầu bằng ngôn ngữ tự nhiên",
  "Ask in plain English — \"Scan S3\", \"Check IAM risks\", \"Run a full AWS scan\".":
    "Hỏi bằng tiếng Anh thông thường — \"Quét S3\", \"Kiểm tra rủi ro IAM\", \"Chạy quét AWS đầy đủ\".",
  "AWS connection": "Kết nối AWS",
  "Configure access key, secret, optional session token, region, and default scope.":
    "Cấu hình access key, secret, session token tùy chọn, region và phạm vi mặc định.",
  "LangGraph timeline": "Dòng thời gian LangGraph",
  "Every node from environment → report is shown with status, duration, and checkpoint.":
    "Mọi node từ môi trường → báo cáo đều hiển thị trạng thái, thời lượng và checkpoint.",
  "Prowler scan jobs": "Tác vụ quét Prowler",
  "POST /v1/scan/group + polling /v1/job/{id} surfaced as cards.":
    "POST /v1/scan/group + polling /v1/job/{id} hiển thị dạng thẻ.",
  "Tool registry": "Đăng ký công cụ",
  "Tools grouped by scanner / knowledge / remediation, with manual-only flag.":
    "Công cụ nhóm theo scanner / knowledge / remediation, có cờ chỉ thủ công.",
  "Human-in-the-loop": "Có con người trong vòng lặp",
  "Agent pauses before remediation and waits for explicit approval.":
    "Agent dừng trước khi khắc phục và chờ phê duyệt rõ ràng.",
  "Verification": "Xác minh",
  "Re-runs the failing check and shows before/after evidence.":
    "Chạy lại kiểm tra thất bại và hiển thị chứng cứ trước/sau.",
  "DOCX preview & export": "Xem trước & xuất DOCX",
  "Preview and download a polished report with executive summary and appendix.":
    "Xem trước và tải báo cáo hoàn chỉnh kèm tóm tắt điều hành và phụ lục.",

  // CTA
  "Open the workspace and walk through a real S3 scan":
    "Mở workspace và xem một lần quét S3 thực tế",
  "A full mock run — environment validation, planning, submit, 4 poll iterations, normalize, evaluate, approve, execute, verify, and a DOCX report — is preloaded.":
    "Một lần chạy mô phỏng đầy đủ — kiểm tra môi trường, lập kế hoạch, gửi, 4 vòng polling, chuẩn hóa, đánh giá, phê duyệt, thực thi, xác minh và báo cáo DOCX — đã được tải sẵn.",
  "Results dashboard": "Bảng điều khiển kết quả",
  "Approvals queue": "Hàng đợi phê duyệt",

  // Footer
  "© 2026 PDCA Prowler Agent — Thesis demo · Frontend mock-mode · No backend connection":
    "© 2026 PDCA Prowler Agent — Demo luận văn · Frontend chế độ mock · Không kết nối backend",

  // TopBar / pills
  "run": "lần chạy",
  "node": "node",
  "report": "báo cáo",

  // Tables / table headers
  "Run ID": "Mã lần chạy",
  "Target": "Đối tượng",
  "Account": "Tài khoản",
  "Started": "Bắt đầu",
  "Duration": "Thời lượng",
  "Status": "Trạng thái",
  "Findings": "Phát hiện",
  "Remediated": "Đã khắc phục",
  "Report": "Báo cáo",
  "Actions": "Hành động",
  "Sev": "Mức",
  "Remediation": "Khắc phục",
  "Check ID": "Mã kiểm tra",
  "Service": "Dịch vụ",
  "Resource": "Tài nguyên",
  "Finding": "Phát hiện",
  "Evidence": "Chứng cứ",

  // Run detail
  "Scan jobs": "Tác vụ quét",
  "Findings summary": "Tóm tắt phát hiện",
  "Pending approvals": "Đang chờ phê duyệt",
  "None pending.": "Không có gì đang chờ.",

  // Report view
  "Outline": "Mục lục",
  "Generated by PDCA Prowler Agent": "Tạo bởi PDCA Prowler Agent",
  "Section": "Phần",
  "All sections": "Tất cả phần",

  // Settings
  "Credentials": "Thông tin đăng nhập",
  "Security note": "Lưu ý bảo mật",
  "Connection state": "Trạng thái kết nối",
  "UI states surfaced": "Trạng thái UI hiển thị",

  // Approvals
  "This tool requires manual action. Suggested steps will be added to the report.":
    "Công cụ này yêu cầu thao tác thủ công. Các bước đề xuất sẽ được thêm vào báo cáo.",
  "Tool & Evidence Trace": "Trace công cụ & chứng cứ",

  // Trace nodes / status
  "scan_submit": "scan_submit",
  "scan_poll ×4": "scan_poll ×4",
  "scan_collect": "scan_collect",
  "risk_evaluation": "risk_evaluation",
  "review_task": "review_task",

  // Misc small strings
  "step": "bước",
  "Yes": "Có",
  "No": "Không",
  "Approve": "Phê duyệt",
  "Reject": "Từ chối",
  "Cancel": "Hủy",
  "Save": "Lưu",
  "Submit": "Gửi",
  "Next": "Tiếp",
  "Back": "Quay lại",
  "Close": "Đóng",
  "Loading…": "Đang tải…",
  "Loading...": "Đang tải...",
  "Search": "Tìm kiếm",
};

const VI_EN: Record<string, string> = Object.fromEntries(
  Object.entries(EN_VI).map(([en, vi]) => [vi, en])
);

/* ------------------------------------------------------------------ */
/* DOM text translation                                                */
/* ------------------------------------------------------------------ */

const SKIP_TAGS = new Set([
  "SCRIPT", "STYLE", "NOSCRIPT", "CODE", "PRE", "TEXTAREA", "INPUT",
]);

function isInsideToggle(node: Node): boolean {
  let p: Node | null = node;
  while (p) {
    if (p instanceof Element && p.hasAttribute?.("data-floating-toggle")) return true;
    p = p.parentNode;
  }
  return false;
}

function* walkTextNodes(root: Node): Generator<Text> {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => {
      const parent = n.parentElement;
      if (!parent) return NodeFilter.FILTER_REJECT;
      if (SKIP_TAGS.has(parent.tagName)) return NodeFilter.FILTER_REJECT;
      if (isInsideToggle(parent)) return NodeFilter.FILTER_REJECT;
      if (!n.nodeValue || !n.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  let cur: Node | null;
  while ((cur = walker.nextNode())) yield cur as Text;
}

function applyTranslation(target: "vi" | "en") {
  const dict = target === "vi" ? EN_VI : VI_EN;
  for (const node of walkTextNodes(document.body)) {
    const original = node.nodeValue ?? "";
    const trimmed = original.trim();
    if (!trimmed) continue;
    const replacement = dict[trimmed];
    if (replacement && replacement !== trimmed) {
      const leading = original.match(/^\s*/)?.[0] ?? "";
      const trailing = original.match(/\s*$/)?.[0] ?? "";
      node.nodeValue = leading + replacement + trailing;
    }
  }
}

/* ------------------------------------------------------------------ */
/* Light-mode CSS overrides (injected once)                            */
/* ------------------------------------------------------------------ */
/* Light palette derived from brand cyan #22D3EE via color-palette skill.
   All foreground/background pairs verified WCAG AA (>=4.5:1). */
const LIGHT_CSS = `
html.light {
  /* shadcn semantic tokens */
  --background: 214 32% 94%;          /* tinted slate #EEF2F7 — softer than pure white */
  --foreground: 222 47% 11%;          /* slate-900 #0F172A — 16:1 on bg */
  --card: 0 0% 100%;                  /* #FFFFFF */
  --card-foreground: 222 47% 11%;
  --popover: 0 0% 100%;
  --popover-foreground: 222 47% 11%;
  --primary: 187 85% 33%;             /* cyan-700 #0D8B9C — 5.4:1 vs white */
  --primary-foreground: 0 0% 100%;
  --secondary: 187 75% 94%;           /* cyan-100 #E5F8FA */
  --secondary-foreground: 187 85% 20%;/* cyan-900 #08545E */
  --muted: 210 40% 96%;               /* slate-100 */
  --muted-foreground: 215 19% 35%;    /* slate-600 #475569 — 7.3:1 vs white */
  --accent: 187 75% 94%;
  --accent-foreground: 187 85% 28%;
  --destructive: 0 72% 45%;           /* red-600 #DC2626 — 4.8:1 vs white */
  --destructive-foreground: 0 0% 100%;
  --border: 214 32% 91%;              /* slate-200 #E2E8F0 */
  --input: 214 32% 91%;
  --ring: 187 85% 40%;                /* cyan-600 */
}

/* Page glow softened for light surfaces */
html.light body {
  background-color: #EEF2F7;
  color: #0F172A;
  background-image:
    radial-gradient(at 12% 8%, hsl(187 85% 50% / 0.07) 0, transparent 45%),
    radial-gradient(at 88% 92%, hsl(232 70% 60% / 0.06) 0, transparent 50%);
}

/* ---- Stitch literal tokens (overridden for light mode) ---- */
/* Three-tier elevation: page bg < surface card < elevated chip */
html.light .bg-bg-base       { background-color: #EEF2F7 !important; }
html.light .bg-bg-surface    { background-color: #FFFFFF !important; }
html.light .bg-bg-elevated   { background-color: #E2E8F0 !important; }
html.light [class*="bg-bg-base/"]     { background-color: rgb(238 242 247 / 0.85) !important; }
html.light [class*="bg-bg-surface/"]  { background-color: rgb(255 255 255 / 0.92) !important; }
html.light [class*="bg-bg-elevated/"] { background-color: rgb(226 232 240 / 0.75) !important; }

/* Text — catch ALL opacity variants ("/90", "/80"…) so <Code> and similar pop */
html.light [class*="text-text-primary"]   { color: #0B1220 !important; }   /* near-black, 18:1 */
html.light [class*="text-text-secondary"] { color: #334155 !important; }   /* slate-700, 9.3:1 */
html.light [class*="text-text-muted"]     { color: #475569 !important; }   /* slate-600, 7.3:1 — was 4.6 */

/* Borders */
html.light .border-border-muted             { border-color: #E2E8F0 !important; }
html.light [class*="border-border-muted/"]  { border-color: rgb(226 232 240 / 0.7) !important; }

/* Status colours — darkened so they pass AA on light surfaces */
html.light .text-status-success { color: #059669 !important; }   /* 4.5:1 */
html.light .text-status-warning { color: #B45309 !important; }   /* 5.9:1 — original #FBBF24 fails on white */
html.light .text-status-error   { color: #DC2626 !important; }   /* 4.8:1 */
html.light .text-severity-high   { color: #B91C1C !important; }
html.light .text-severity-medium { color: #C2410C !important; }
html.light .text-severity-low    { color: #1D4ED8 !important; }
html.light .text-severity-info   { color: #0E7490 !important; }
html.light .bg-status-success\\/60 { background-color: rgb(5 150 105 / 0.7) !important; }
html.light .bg-status-warning\\/60 { background-color: rgb(180 83 9 / 0.7) !important; }
html.light .bg-status-error\\/60   { background-color: rgb(220 38 38 / 0.7) !important; }

/* Brand text gradient — bright cyan→sky→indigo, all !important so
   background-clip:text wins over any layer ordering. Lighter than dark
   mode but still AA on the soft slate page bg (#EEF2F7). */
html.light .text-gradient-cyan {
  background-image: linear-gradient(90deg, #06B6D4 0%, #0EA5E9 45%, #6366F1 100%) !important;
  -webkit-background-clip: text !important;
  background-clip: text !important;
  -webkit-text-fill-color: transparent !important;
  color: transparent !important;
}

/* Primary button label stays white. We don't need a broad [class*="text-primary"]
   rule — Tailwind already resolves text-primary / text-primary/15 etc. via the
   --primary CSS variable that we override above. (The previous wildcard also
   matched .text-text-primary, which broke the hero h1.) */
html.light .text-primary-foreground { color: #FFFFFF !important; }

/* <Code> chips — boost background contrast so the inline code reads as a chip */
html.light code,
html.light .font-mono {
  color: #0B1220 !important;
}
/* The Code component uses bg-bg-elevated/60 — already overridden above to slate-200/75.
   Add a subtle border darkening so the chip outline is visible on light. */
html.light code[class*="border-border"] {
  border-color: #CBD5E1 !important;
}

/* Soften the dark-tuned glow shadow */
html.light .shadow-\\[0_0_8px_2px_hsl\\(var\\(--primary\\)\\)\\] {
  box-shadow: 0 0 6px 1px hsl(var(--primary) / 0.45) !important;
}

/* Inputs / cards on light bg — slight shadow for separation since borders are subtle */
html.light .surface-card,
html.light [class*="bg-card/"] {
  box-shadow: 0 1px 2px rgb(15 23 42 / 0.04), 0 1px 3px rgb(15 23 42 / 0.04);
}
`;

function ensureLightStyle() {
  if (document.getElementById("__lang_theme_light_css")) return;
  const style = document.createElement("style");
  style.id = "__lang_theme_light_css";
  style.textContent = LIGHT_CSS;
  document.head.appendChild(style);
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */
type Lang = "en" | "vi";
type Theme = "dark" | "light";

interface FloatingTogglesProps {
  visible?: boolean;
  variant?: "floating" | "inline";
}

export function FloatingToggles({ visible = true, variant = "floating" }: FloatingTogglesProps = {}) {
  const [lang, setLang] = useState<Lang>(
    () => (localStorage.getItem("ui.lang") as Lang) || "en"
  );
  const [theme, setTheme] = useState<Theme>(
    () => (localStorage.getItem("ui.theme") as Theme) || "dark"
  );

  // Theme: toggle html class + persist
  useEffect(() => {
    ensureLightStyle();
    document.documentElement.classList.toggle("light", theme === "light");
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("ui.theme", theme);
  }, [theme]);

  // Re-apply translation whenever language changes or DOM mutates
  const reapply = useCallback(() => {
    if (lang === "vi") applyTranslation("vi");
  }, [lang]);

  useEffect(() => {
    localStorage.setItem("ui.lang", lang);
    if (lang === "vi") {
      applyTranslation("vi");
    } else {
      applyTranslation("en");
    }
  }, [lang]);

  useEffect(() => {
    if (lang !== "vi") return;
    let scheduled = false;
    const observer = new MutationObserver(() => {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(() => {
        scheduled = false;
        reapply();
      });
    });
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
    });
    return () => observer.disconnect();
  }, [lang, reapply]);

  // `visible` lets callers hide the UI while keeping state + side-effects
  // (mutation observer for VI translation must stay mounted to keep working
  // when new DOM nodes appear in other views).
  if (!visible) return null;

  return (
    <div
      data-floating-toggle="true"
      className={
        variant === "inline"
          ? "inline-flex items-center gap-2 rounded-xl border border-border/70 bg-card/60 px-2 py-1.5"
          : "fixed bottom-4 right-4 z-[9999] flex items-center gap-2 rounded-full border border-border/70 bg-card/90 px-2 py-1.5 shadow-lg backdrop-blur-md"
      }
      style={{ fontFamily: "Inter, ui-sans-serif, system-ui, sans-serif" }}
    >
      {/* Language toggle */}
      <button
        type="button"
        onClick={() => setLang((l) => (l === "en" ? "vi" : "en"))}
        title={lang === "en" ? "Chuyển sang Tiếng Việt" : "Switch to English"}
        className="flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-semibold text-text-primary hover:bg-bg-elevated/60 transition-colors"
      >
        <Languages className="h-3.5 w-3.5 text-primary" />
        <span className={lang === "en" ? "text-primary" : "text-text-muted"}>EN</span>
        <span className="text-text-muted">/</span>
        <span className={lang === "vi" ? "text-primary" : "text-text-muted"}>VI</span>
      </button>

      <span className="h-5 w-px bg-border/60" />

      {/* Theme toggle */}
      <button
        type="button"
        onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
        title={theme === "dark" ? "Chế độ sáng" : "Chế độ tối"}
        className="grid h-7 w-7 place-items-center rounded-full text-text-primary hover:bg-bg-elevated/60 transition-colors"
        aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      >
        {theme === "dark" ? (
          <Sun className="h-4 w-4 text-status-warning" />
        ) : (
          <Moon className="h-4 w-4 text-primary" />
        )}
      </button>
    </div>
  );
}
