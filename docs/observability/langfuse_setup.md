# Langfuse Setup Guide

> Hướng dẫn lấy credentials Langfuse cho Phase F + I của implementation plan.
> Tham chiếu: [LANGFUSE_IMPLEMENTATION_PLAN.md §0 P0.1](../LANGFUSE_IMPLEMENTATION_PLAN.md), [LANGFUSE_INTEGRATION_GUIDE.md D2](../LANGFUSE_INTEGRATION_GUIDE.md).

---

## Quyết định cloud vs self-host

| Use case | Khuyến nghị |
|---|---|
| Phát triển local + LVTN demo | **Cloud free tier** — zero ops, đủ cho ~6 typical run/ngày |
| Production / khách hàng thực | **Self-host** — data residency, unlimited observations |
| CI / test | KHÔNG cần Langfuse — dùng mock |

---

## Option A — Cloud (dev / LVTN demo)

### Bước 1. Tạo account
1. Truy cập https://cloud.langfuse.com.
2. Sign up bằng email hoặc GitHub OAuth.
3. Tạo Organization + Project mới (e.g. `pdca-aws-security`).

### Bước 2. Lấy API keys
1. Vào project → **Settings** → **API Keys**.
2. **Create new API key**:
   - Public Key: `pk-lf-...`
   - Secret Key: `sk-lf-...` (lưu ngay, không hiển thị lại).
3. Host mặc định: `https://cloud.langfuse.com` (EU region) hoặc `https://us.cloud.langfuse.com` (US region).

### Bước 3. Cấu hình `.env`
```
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxxxxxxxxxxxxxx
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_REDACT_MODE=full        # BẮT BUỘC cho cloud — bảo vệ AWS account_id
LANGFUSE_ENVIRONMENT=dev
```

### Quota notice
- Free tier: **50K observations/tháng** (~6 typical PDCA run/ngày).
- Bench runner mặc định OFF (`LANGFUSE_BENCH_ENABLED=false`) để bảo vệ quota.
- Hobby tier $29/mo: 100K observations.
- Khi bật cho 1 PR review thì chỉ chạy ad-hoc, không lo cháy quota.

---

## Option B — Self-host (production)

### Yêu cầu
- Docker + Docker Compose v2.
- Postgres + Clickhouse persisting volume (~10GB cho 1 năm trace).
- Reverse proxy (nginx/Caddy) cho HTTPS.

### Bước 1. Clone repo Langfuse
```bash
git clone https://github.com/langfuse/langfuse.git
cd langfuse
```

### Bước 2. Cấu hình `.env` của Langfuse
- Đặt `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY` (xem `.env.prod.example` của Langfuse).
- Set `TELEMETRY_ENABLED=false` cho enterprise privacy.

### Bước 3. Chạy
```bash
docker compose up -d
```

### Bước 4. Tạo project + API keys (như Option A bước 1–2 nhưng UI ở `http://localhost:3000`)

### Bước 5. Cấu hình `.env` của PDCA
```
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-xxxx
LANGFUSE_SECRET_KEY=sk-lf-xxxx
LANGFUSE_HOST=https://langfuse.your-domain.internal
LANGFUSE_REDACT_MODE=internal    # Self-host private network — keep ARN/account
LANGFUSE_ENVIRONMENT=prod
```

### Tham chiếu chính thức
- https://langfuse.com/docs/deployment/self-host

---

## Verification

Sau khi setup, chạy:
```bash
python scripts/verify_langfuse_preflight.py
```

Output phải thấy:
```
[ OK  ] P0.1 Langfuse keys present, host=...
```

Sau Phase F merged, smoke test:
```bash
LANGFUSE_ENABLED=true python -c "
from pdca.observability.langfuse_client import get_langfuse_client
client = get_langfuse_client()
print('client init:', client is not None)
"
```

---

## Rủi ro phổ biến

| Symptom | Khả năng |
|---|---|
| `Langfuse` init raise nhưng pipeline vẫn chạy | Đúng thiết kế — D8 best-effort isolation |
| 0 trace trong UI dù `enabled=true` | Sai key / network block / circuit breaker tripped — check log |
| Trace có root nhưng thiếu generation | LangChain version mismatch — pin `langchain-ollama>=1.0` |
| Token usage = 0 | ChatOllama version không expose `usage_metadata` — verify P0.2 |
| Account_id leak | `LANGFUSE_REDACT_MODE` sai — force `full` ở cloud |

---

## Branch convention (P0.5)

Khi bắt đầu Phase F:
```bash
git checkout main && git pull
git checkout -b feat/langfuse-foundation
```

Khi bắt đầu Phase I (sau Phase F merged):
```bash
git checkout main && git pull
git checkout -b feat/langfuse-instrumentation
```

KHÔNG branch trực tiếp từ branch khác để tránh merge conflict.
