// Phase 0 — mock classifier + canned QA answers.
// Replaced in Phase 1 by backend /v1/chat with real LLM classifier + RAG.

import type {
  IntentKind, IntentMeta, QAAnswerCard, SuggestActionCard, SuggestionChip,
} from "@/types/pdca";

// ───────────── Mock classifier (regex-based) ─────────────
// Returns intent + confidence. Confidence < 0.8 forces "mixed" so the UI
// shows suggestion chips — same behaviour the backend will have in Phase 1.

const QA_MARKERS = [
  "what is", "what's", "why", "how", "explain",
  "là gì", "là sao", "tại sao", "làm sao", "giải thích",
  "khác nhau", "vs", "?",
];
const SCAN_VERBS = [
  "scan", "audit", "check my", "run scan",
  "quét", "kiểm tra", "rà soát",
];
const KNOWN_SERVICES = [
  "s3", "iam", "ec2", "rds", "kms", "ecr", "vpc", "cloudtrail", "guardduty",
];

function hasAny(text: string, needles: string[]): boolean {
  return needles.some((n) => text.includes(n));
}

export function mockClassify(prompt: string): IntentMeta {
  const p = prompt.toLowerCase().trim();
  const hasQA = hasAny(p, QA_MARKERS);
  const hasScan = hasAny(p, SCAN_VERBS);
  const hasSvc = KNOWN_SERVICES.some((s) => new RegExp(`\\b${s}\\b`).test(p));

  // Scan + service is a strong scan signal.
  if (hasScan && hasSvc) return { classified: "scan", confidence: 0.92, reason: "scan verb + service" };

  // Pure question marker → qa.
  if (hasQA && !hasScan) return { classified: "qa", confidence: 0.85, reason: "question marker" };

  // Both signals → mixed.
  if (hasQA && hasScan) return { classified: "mixed", confidence: 0.65, reason: "qa + scan signals" };

  // Service alone without verb → ambiguous mixed.
  if (hasSvc && !hasQA && !hasScan) return { classified: "mixed", confidence: 0.6, reason: "service mention only" };

  // Default fallback: treat as QA.
  return { classified: "qa", confidence: 0.55, reason: "fallback" };
}

// ───────────── Canned QA answers ─────────────
// Lightweight keyword match for the demo. Real backend uses RAG + LLM.

interface QATemplate {
  match: RegExp;
  markdown: string;
  sources: QAAnswerCard["sources"];
}

const QA_TEMPLATES: QATemplate[] = [
  {
    match: /s3.*public|public.*s3|s3 public access/i,
    markdown: `**S3 Block Public Access (BPA)** là cơ chế bảo vệ ở 4 mức:

| Setting | Tác dụng |
|---|---|
| \`BlockPublicAcls\` | Chặn ACL mới cho phép public read/write |
| \`IgnorePublicAcls\` | Bỏ qua ACL public đã tồn tại |
| \`BlockPublicPolicy\` | Chặn bucket policy public |
| \`RestrictPublicBuckets\` | Hạn chế truy cập public qua policy |

\`\`\`bash
aws s3api put-public-access-block \\
  --bucket my-bucket \\
  --public-access-block-configuration \\
    BlockPublicAcls=true,IgnorePublicAcls=true,\\
    BlockPublicPolicy=true,RestrictPublicBuckets=true
\`\`\`

Khuyến nghị: bật **cả 4 ở account level** trừ khi bucket cần phục vụ static website.`,
    sources: [
      { checkId: "s3_account_level_public_access_blocks", title: "S3 — Account-level BPA enabled", score: 0.94 },
      { checkId: "s3_bucket_level_public_access_block", title: "S3 — Bucket-level BPA enabled", score: 0.89 },
      { title: "AWS Docs: Blocking public access to S3", url: "https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html" },
    ],
  },
  {
    match: /iam.*risk|iam risks|iam best/i,
    markdown: `**Rủi ro IAM phổ biến** (theo CIS AWS Benchmark):

1. **Root account dùng access key** — luôn xoá, dùng IAM user/role thay thế.
2. **MFA chưa bật** cho root + IAM user có console access.
3. **Wildcard policy** \`"Action": "*"\` hoặc \`"Resource": "*"\` không kèm condition.
4. **Access key cũ hơn 90 ngày** không rotate.
5. **IAM user không cần thiết** — ưu tiên IAM Identity Center (SSO) + role assumption.
6. **Inline policy** thay vì managed policy → khó audit.

\`\`\`bash
# Tìm user có access key cũ
aws iam list-users --query 'Users[].UserName' \\
  | xargs -I{} aws iam list-access-keys --user-name {}
\`\`\``,
    sources: [
      { checkId: "iam_root_hardware_mfa_enabled", title: "Root MFA hardware enabled", score: 0.91 },
      { checkId: "iam_user_no_setup_initial_access_key", title: "No initial access key on user creation", score: 0.86 },
      { checkId: "iam_rotate_access_key_90_days", title: "Rotate access keys ≤ 90 days", score: 0.84 },
    ],
  },
  {
    match: /encryption|encrypt|mã hoá/i,
    markdown: `**Encryption at rest** trên AWS có 2 lớp:

- **Server-side (SSE)**: AWS-managed key (\`SSE-S3\`), KMS key (\`SSE-KMS\`), hoặc customer-provided (\`SSE-C\`).
- **Client-side**: encrypt trước khi upload.

Khuyến nghị **SSE-KMS với customer-managed key (CMK)** vì:
- Audit qua CloudTrail mọi lần dùng key
- Rotate key tự động
- Tách quyền: ai dùng key ≠ ai quản key

\`\`\`json
{
  "ServerSideEncryptionConfiguration": {
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "aws:kms",
        "KMSMasterKeyID": "arn:aws:kms:us-east-1:111:key/abc"
      },
      "BucketKeyEnabled": true
    }]
  }
}
\`\`\``,
    sources: [
      { checkId: "s3_bucket_default_encryption", title: "S3 bucket default encryption", score: 0.93 },
      { checkId: "s3_bucket_kms_encryption", title: "S3 bucket KMS encryption", score: 0.88 },
    ],
  },
];

const FALLBACK_QA: QAAnswerCard = {
  kind: "qa_answer",
  markdown: `Tôi chưa có câu trả lời sẵn cho câu hỏi này trong demo (Phase 0 mock).

Khi backend live, agent sẽ truy vấn **RAG service** để retrieve các Prowler check + AWS docs liên quan, rồi sinh câu trả lời có nguồn.

Bạn có thể thử các câu hỏi mẫu:
- *"S3 public access là gì?"*
- *"IAM risks phổ biến"*
- *"Encryption at rest trên S3"*

Hoặc gõ \`scan s3\` để chạy pipeline PDCA scan thật.`,
  sources: [],
};

export function mockAnswerQA(prompt: string, intent: IntentMeta): QAAnswerCard {
  for (const t of QA_TEMPLATES) {
    if (t.match.test(prompt)) {
      return {
        kind: "qa_answer",
        markdown: t.markdown,
        sources: t.sources,
        intentMeta: intent,
      };
    }
  }
  return { ...FALLBACK_QA, intentMeta: intent };
}

// ───────────── Suggestion chips ─────────────
// Generated when intent is "mixed" — let the user disambiguate.

export function mockSuggestChips(prompt: string): SuggestActionCard {
  const p = prompt.toLowerCase();
  const service = KNOWN_SERVICES.find((s) => new RegExp(`\\b${s}\\b`).test(p));

  const chips: SuggestionChip[] = [];
  if (service) {
    chips.push({
      label: `Giải thích rủi ro ${service.toUpperCase()}`,
      icon: "qa",
      intent: "qa",
      payload: `What are common ${service} risks?`,
    });
    chips.push({
      label: `Quét ${service.toUpperCase()} trong account`,
      icon: "scan",
      intent: "scan",
      payload: `scan ${service}`,
    });
    chips.push({
      label: `Xem findings ${service.toUpperCase()} gần nhất`,
      icon: "evidence",
      intent: "qa",
      payload: `Show recent ${service} findings`,
    });
  } else {
    chips.push(
      { label: "Giải thích AWS security basics", icon: "qa", intent: "qa", payload: "What are AWS security best practices?" },
      { label: "Quét S3 trong account", icon: "scan", intent: "scan", payload: "scan s3" },
      { label: "Xem báo cáo gần nhất", icon: "report", intent: "qa", payload: "Show last report summary" },
    );
  }

  return {
    kind: "suggest_action",
    prompt: "Bạn muốn tôi:",
    chips,
  };
}

// Helper used by FE to "send" a chip's payload as if the user typed it.
export function intentLabel(intent: IntentKind): string {
  switch (intent) {
    case "qa": return "Q&A";
    case "scan": return "Scan";
    case "mixed": return "Ambiguous";
  }
}
