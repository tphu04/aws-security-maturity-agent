# Langfuse Self-Host — PDCA AWS Security Agent

Deploy artifacts cho Langfuse v3 (Postgres + Clickhouse + Redis + MinIO + web + worker).
Phù hợp cho LVTN demo / production nội bộ. Tham chiếu spec: [docs/observability/langfuse_setup.md §Option B](../../docs/observability/langfuse_setup.md).

---

## Quickstart

```bash
cd deploy/langfuse

# 1. Sinh .env với secrets random + bootstrap project tự động
bash scripts/generate-secrets.sh

# 2. Pull + start stack (lần đầu ~3–5 phút)
docker compose pull
docker compose up -d

# 3. Chờ healthy
docker compose ps
```

Khi `langfuse-web` healthy → mở http://localhost:3010.

Login bằng email/password in ra ở bước 1 (`admin@pdca.local`).
Project + API keys đã được auto-bootstrap, không cần click UI tạo.

---

## Cấu hình PDCA dùng instance self-host này

Copy 3 dòng `LANGFUSE_*` từ output script vào file `.env` ở repo root:

```env
LANGFUSE_ENABLED=true
LANGFUSE_PUBLIC_KEY=pk-lf-...        # từ generate-secrets.sh
LANGFUSE_SECRET_KEY=sk-lf-...        # từ generate-secrets.sh
LANGFUSE_HOST=http://localhost:3010
LANGFUSE_REDACT_MODE=internal        # self-host private — giữ ARN/account để debug
LANGFUSE_ENVIRONMENT=prod
```

Verify:
```bash
python scripts/verify_langfuse_preflight.py
```

Smoke 1 trace:
```bash
LANGFUSE_ENABLED=true python -c "
from pdca.observability.tracing import start_trace, end_trace, span
from pdca.observability.langfuse_client import flush_safe
import uuid
rid = str(uuid.uuid4())
h = start_trace(rid, user_request='self-host smoke', environment='prod')
with span('node:smoke', input={'ok': True}) as s:
    s.update(output={'done': True})
end_trace(h); flush_safe()
print('trace:', rid)
"
```

Mở Langfuse UI → Traces → tìm trace với `id` in ra.

---

## Layout

| File | Mục đích |
|---|---|
| `docker-compose.yml` | Stack chính thức từ Langfuse (pinned `:3` major). Secrets bắt buộc qua `.env`. |
| `.env.example` | Template biến môi trường — không có secret thật. |
| `.env` | (gitignored) sinh bởi script. |
| `scripts/generate-secrets.sh` | Sinh `.env` random secrets + bootstrap PDCA project. Chạy bằng Git Bash. |

---

## Port mapping

| Service | Host port | Mục đích |
|---|---|---|
| langfuse-web | 3010 | UI + API |
| langfuse-worker | 127.0.0.1:3030 | Internal worker (debug) |
| postgres (Langfuse) | 127.0.0.1:5433 | **Lệch khỏi 5432 để tránh đụng Postgres local PDCA** |
| clickhouse HTTP | 127.0.0.1:8123 | Query trace storage |
| clickhouse native | 127.0.0.1:9000 | Native protocol |
| minio S3 | 9090 | S3-compatible upload endpoint |
| minio console | 127.0.0.1:9091 | Bucket browser |
| redis | 127.0.0.1:6379 | Queue |

Nếu port đụng (vd. PDCA RAG dùng 8000, OK vì Langfuse không đụng), đổi trong `.env`.

---

## Operations

```bash
# Logs realtime
docker compose logs -f langfuse-web langfuse-worker

# Stop (giữ data)
docker compose down

# Stop + xoá data (RESET sạch — mất hết trace lịch sử)
docker compose down -v

# Backup volumes (Postgres + Clickhouse + MinIO)
docker run --rm -v langfuse_langfuse_postgres_data:/data -v "$(pwd):/backup" \
  alpine tar czf /backup/pg-$(date +%Y%m%d).tar.gz -C /data .
```

---

## Troubleshooting

| Triệu chứng | Cách xử lý |
|---|---|
| `langfuse-web` restart loop, log `ENCRYPTION_KEY` invalid | Phải đúng 64 hex chars. Re-run `generate-secrets.sh`. |
| `langfuse-worker` báo Clickhouse migration fail | `docker compose down clickhouse && docker compose up -d clickhouse`, chờ healthy, rồi `up -d langfuse-worker`. |
| PDCA verify_langfuse_preflight báo `host unreachable` | Kiểm tra `docker compose ps` có `Up (healthy)`. Test: `curl http://localhost:3010/api/public/health`. |
| 0 trace trên UI dù pipeline chạy | Check `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` PDCA `.env` khớp với `LANGFUSE_INIT_PROJECT_*` ở `deploy/langfuse/.env`. |
| Postgres 5433 vẫn đụng | Đổi `POSTGRES_HOST_PORT` trong `deploy/langfuse/.env`, `docker compose up -d`. |

---

## Bảo mật

- `.env` chứa toàn bộ secrets — gitignored, KHÔNG commit.
- Stack mặc định bind 127.0.0.1 cho mọi service trừ `3010` (web) và `9090` (minio S3).
- Nếu expose ra LAN/Internet: bắt buộc reverse proxy HTTPS (nginx/Caddy) trước host port 3010 + restrict `9090` qua firewall.
- Production: đặt `LANGFUSE_REDACT_MODE=full` ở PDCA `.env` nếu Langfuse host không nằm trong cùng vùng tin cậy với AWS account.
