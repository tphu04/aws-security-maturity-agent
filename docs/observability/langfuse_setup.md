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

## Option B — Self-host (production / LVTN demo nội bộ)

### Tổng quan kiến trúc
Stack Langfuse v3 gồm 6 services:

| Service | Image | Vai trò |
|---|---|---|
| `langfuse-web` | `langfuse/langfuse:3` | Next.js UI + REST/SDK ingest API (port 3000) |
| `langfuse-worker` | `langfuse/langfuse-worker:3` | Background job consumer (clickhouse write, batch export) |
| `postgres` | `postgres:17` | Metadata: org/project/user/keys/scores |
| `clickhouse` | `clickhouse/clickhouse-server` | Trace storage (cột-based, query nhanh) |
| `redis` | `redis:7` | Queue ingest events giữa web ↔ worker |
| `minio` | `chainguard/minio` | S3-compatible blob store (event payload + media uploads) |

Repo đã pin sẵn compose + script tự động hóa tại [`deploy/langfuse/`](../../deploy/langfuse/).

### Yêu cầu môi trường
- **Docker Desktop ≥ 4.30** (Compose v2 built-in). Verify: `docker --version && docker compose version`.
- **Disk**: ≥ 10GB free (~2GB images + volume tăng dần theo lượng trace).
- **RAM**: ≥ 4GB cho stack (Clickhouse là service nặng nhất).
- **Bash**: cần để chạy `generate-secrets.sh`. Trên Windows dùng Git Bash đi kèm Git for Windows.
- **OpenSSL**: kèm Git Bash. Verify: `openssl version`.

### Bước 1. Lấy deploy artifacts
Repo PDCA đã có sẵn — không cần clone Langfuse:

```bash
cd c:/Users/trung/Desktop/DoAn        # hoặc đường dẫn repo của bạn
ls deploy/langfuse/                    # docker-compose.yml, .env.example, README.md, scripts/
```

> Nếu cần update lên major Langfuse mới hơn: edit `deploy/langfuse/docker-compose.yml`,
> đổi tag `:3` thành `:4` (khi Langfuse phát hành), test riêng trước khi áp prod.

### Bước 2. Sinh secrets + bootstrap project
```bash
cd deploy/langfuse
bash scripts/generate-secrets.sh
```

Script sẽ:
1. Sinh 8 secret ngẫu nhiên (`ENCRYPTION_KEY` 64-hex, `NEXTAUTH_SECRET`, `SALT`,
   passwords cho Postgres/Clickhouse/Redis/MinIO + 2 S3 access keys).
2. Sinh `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` (`pk-lf-...`) và `_SECRET_KEY` (`sk-lf-...`)
   — chính là cặp dán vào PDCA `.env`.
3. Sinh password admin user (`admin@pdca.local`).
4. Ghi tất cả vào `deploy/langfuse/.env` (gitignored, `chmod 600`).
5. In ra console 3 dòng PDCA cần + login UI password.

> **Lưu console output** — password admin chỉ in 1 lần. Nếu mất: xoá volume Postgres
> và re-bootstrap (`docker compose down -v && docker compose up -d`).

### Bước 3. Pull images + start stack
```bash
docker compose pull         # ~3–5 phút lần đầu, ~2GB
docker compose up -d        # detach
docker compose ps           # tất cả phải "Up (healthy)" sau ~60s
```

Healthcheck order: postgres → clickhouse → redis → minio → langfuse-worker → langfuse-web.

Theo dõi log realtime:
```bash
docker compose logs -f langfuse-web langfuse-worker
```

Dấu hiệu OK:
- `langfuse-web` log: `▲ Next.js ... Ready in ... ms` và `Listening on port 3000`.
- `langfuse-worker` log: `Worker started ...` (không có ERROR clickhouse migration).

### Bước 4. Verify Langfuse hoạt động
```bash
# Health endpoint (không cần auth)
curl http://localhost:3010/api/public/health
# Kỳ vọng: {"status":"OK","version":"3.x.x"}
```

Mở browser: http://localhost:3010
- Login: `admin@pdca.local` + password ở Bước 2.
- Vào project **PDCA AWS Security Agent** → **Settings → API Keys** → xác nhận có 1
  cặp pre-bootstrapped (public key bắt đầu `pk-lf-`).

### Bước 5. Cấu hình PDCA `.env`
Mở `c:/Users/trung/Desktop/DoAn/.env` (file ở repo root), thay/thêm:

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...        # copy từ output Bước 2
LANGFUSE_SECRET_KEY=sk-lf-...        # copy từ output Bước 2
LANGFUSE_HOST=http://localhost:3010  # self-host local
LANGFUSE_REDACT_MODE=internal        # private — giữ ARN/account để debug
LANGFUSE_ENVIRONMENT=prod            # filter UI
LANGFUSE_FLUSH_AT_NODE=true
LANGFUSE_BENCH_ENABLED=false
LANGFUSE_SAMPLE_RATE=1.0
```

Chú ý: nếu Langfuse host trên LAN/VPS khác, thay `localhost:3010` bằng URL thực
(và nên đặt sau reverse proxy HTTPS — xem Bước 9).

### Bước 6. Preflight verify
```bash
cd c:/Users/trung/Desktop/DoAn
python scripts/verify_langfuse_preflight.py
```

Kỳ vọng:
```
[ OK  ] P0.1 Langfuse keys present, host=http://localhost:3010
[ OK  ] P0.2 ChatOllama source has usage_metadata + eval_count + input_tokens
[ OK  ] Langfuse SDK installed: 3.x.x
```

### Bước 7. Smoke test 1 trace tay
```bash
python -c "
from pdca.observability.tracing import start_trace, end_trace, span
from pdca.observability.langfuse_client import flush_safe, shutdown
import uuid
rid = str(uuid.uuid4())
h = start_trace(rid, user_request='self-host smoke', environment='prod')
with span('node:smoke', input={'check': 'A1'}, metadata={'phase': 'demo'}) as s:
    s.update(output={'finding': 'all good'})
end_trace(h); flush_safe(); shutdown()
print('trace_id:', rid)
"
```

Mở Langfuse UI → **Tracing → Traces** → tìm trace có `id` = `trace_id` in ra.
Kỳ vọng thấy: 1 root `pdca.run` → 1 span con `node:smoke` với input/output đã ghi.

### Bước 8. E2E test với pipeline thật
Chạy 1 PDCA assessment cycle (cần Ollama + RAG + AWS creds đã setup):

```bash
# Terminal 1: RAG service
cd RAG && uvicorn app.main:app --port 8000

# Terminal 2: PDCA scanner API server
python -m pdca.api_server

# Terminal 3: PDCA orchestrator (1 run)
python -m pdca.orchestrator
# nhập user_request: "scan s3 bucket cho public access"
```

Khi pipeline chạy xong, mở Langfuse UI:
- **Traces** → trace mới nhất → tree view phải có topology:
  ```
  pdca.run
  ├── node:environment → aws:sts:get_caller_identity, aws:s3:list_buckets
  ├── node:planning → agent:PlanningAgent → (LLM generation)
  ├── node:scan_submit → scanner:start_scan_by_*
  ├── node:scan_poll[iter=N] → scanner:check_job_status
  ├── node:risk_evaluation → agent:RiskEvaluationAgent → risk.pass1, risk.pass2_rag
  ├── node:operational_planning → agent:RemediationPlannerAgent
  ├── hitl:wait
  ├── node:execution → tool:<remediation_tool>
  ├── node:verification → agent:AnalysisAgent
  └── node:report → maturity:assess, agent:ReportAgent → report.section.* × ~15
  ```
- **Metadata** tab: `pdca.outcome.tag` ∈ `{success, partial_failure, degraded}`.
- **Scores** tab: `planning_top_score`, `risk_severity_critical`, `outcome_fixed_ratio`,
  `validation_issues`.
- **Token usage** tab: model `gemma3:4b` với `prompt_tokens`/`completion_tokens` > 0.

Nếu thiếu phần nào → check [docs/observability/runbook.md §4](runbook.md) failure modes.

### Bước 9. Hardening cho production (optional)
1. **Reverse proxy HTTPS** trước host port 3010 (nginx/Caddy):
   ```nginx
   server {
     listen 443 ssl;
     server_name langfuse.example.internal;
     ssl_certificate /etc/letsencrypt/live/.../fullchain.pem;
     ssl_certificate_key /etc/letsencrypt/live/.../privkey.pem;
     location / {
       proxy_pass http://localhost:3010;
       proxy_set_header Host $host;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto https;
     }
   }
   ```
   Sửa `deploy/langfuse/.env`: `NEXTAUTH_URL=https://langfuse.example.internal`.
2. **Firewall**: chặn ngoài LAN cho port 9090 (MinIO) — chỉ langfuse-worker cần.
3. **Backup tự động Postgres + Clickhouse + MinIO** (cron, xem README.md `Operations`).
4. **Rotate secrets**: re-run `generate-secrets.sh` định kỳ. Lưu ý: thay `ENCRYPTION_KEY`
   sẽ làm mất khả năng giải mã API key cũ — phải tạo lại API keys.
5. **Monitoring**: scrape `http://localhost:3010/api/public/health` → Prometheus.

### Tham chiếu chính thức
- https://langfuse.com/self-hosting/docker-compose
- https://langfuse.com/self-hosting/configuration (full env var reference)
- https://langfuse.com/self-hosting/upgrade

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
