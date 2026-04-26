# AWS Security Maturity Agent

Multi-agent security assessment pipeline triển khai theo chu trình **PDCA**
(Plan → Do → Check → Act) cho hạ tầng AWS. Orchestration bằng **LangGraph**,
LLM reasoning qua **Ollama** (local), retrieval augment qua **RAG service**
(FastAPI + Chroma + BM25), scan gốc bằng **Prowler**.

## Kiến trúc

```
DoAn/
├── pdca/                        # Application package — orchestrator + agents
│   ├── __init__.py
│   ├── state.py                 # PDCAState (LangGraph state schema)
│   ├── config.py                # Service URLs, model names (env-driven)
│   ├── tools.py                 # Remediation tool registry
│   ├── orchestrator.py          # LangGraph workflow (build_graph, nodes)
│   ├── api_server.py            # Prowler Scanner REST API (port 8000)
│   ├── benchmark_report_models.py
│   └── agents/
│       ├── planning_agent.py
│       ├── scanner_agent.py
│       ├── monitoring_agent.py
│       ├── risk_evaluation_agent.py
│       ├── remediate_planner_agent.py
│       ├── execution_agent.py
│       ├── rescan_agent.py
│       ├── analysis_agent.py
│       ├── report_agent.py
│       ├── environment_agent.py
│       ├── assessment_agent.py
│       ├── report_module/       # Report rendering internals
│       │   ├── maturity_engine.py
│       │   ├── llm_writer.py
│       │   ├── llm_validator.py
│       │   ├── template.py
│       │   ├── chart_util.py
│       │   └── exporters.py
│       └── shared/              # Cross-agent utilities
│           ├── rag_client.py
│           ├── normalizer.py
│           └── utils.py
│
├── RAG/                         # Self-contained RAG subproject (port 8005)
│   ├── app/
│   │   ├── main.py              # FastAPI entry
│   │   ├── api/routes/          # /v1/retrieve, /v1/resolve, /health
│   │   ├── context/             # Bundle factory, coverage selector
│   │   ├── retrieval/           # Hybrid pipeline (BM25 + vector + rerank)
│   │   ├── indexing/            # BM25 + Chroma indexes
│   │   ├── ingestion/           # Loaders, normalizers
│   │   ├── evaluation/          # Retrieval metrics (nDCG, MRR, AP…)
│   │   ├── services/            # Check, maturity, mapping, context services
│   │   └── core/                # Config, constants, scoring_config.json
│   ├── scripts/                 # build_all.py, run_benchmark.py…
│   ├── tests/
│   └── data/
│       ├── raw/                 # Curated inputs (tracked)
│       ├── normalized/          # Normalized corpora (tracked)
│       └── indexes/             # BM25 + Chroma (gitignored — regenerated)
│
├── benchmarks/                  # Đánh giá chất lượng — tách khỏi code chạy
│   ├── rag/                     # RAG retrieval benchmarks (was RAG/data/benchmarks/)
│   │   ├── benchmark_retrieval.py
│   │   ├── benchmark_ablation.py
│   │   ├── benchmark_context.py
│   │   ├── benchmark_cases.json
│   │   └── release_criteria.json
│   └── llm_generation/          # LLM generation benchmarks (was benchmark_llm_gen/)
│       ├── runners (run_*_benchmark.py)
│       ├── benchmark_*.py + *_metrics.py
│       ├── cases/criteria JSON
│       └── *.md reports
│
├── data/                        # PDCA pipeline I/O
│   ├── raw/                     # Immutable inputs (tracked)
│   │   └── prowler_checks.json
│   ├── samples/                 # Demo reports (tracked)
│   └── artifacts/               # Runtime outputs (gitignored)
│       ├── pre_scan.json, post_scan.json, analysis_diff.json
│       ├── initial_scan_config.json, performance_metrics.json
│       ├── final_report.{md,html,pdf}
│       ├── charts/
│       └── e2e_snapshots/
│
├── tests/                       # PDCA unit/integration tests
├── scripts/                     # Ops scripts (degrade, e2e runner, sample gen)
├── requirements.txt
└── .env                         # Service URLs + AWS credentials (gitignored)
```

## Yêu cầu

- Python **3.12+**
- [Ollama](https://ollama.com/) chạy local, đã pull model (`ollama pull gemma3:4b`)
- [Prowler](https://docs.prowler.com/) binary accessible trên PATH (dùng bởi Scanner API)
- AWS credentials với quyền đọc + sửa resource target (degrade/remediate)
- (Tuỳ chọn) `wkhtmltopdf` hoặc WeasyPrint để xuất PDF report

## Cài đặt

```bash
git clone <repo-url> DoAn
cd DoAn
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate      # Linux/Mac
pip install -r requirements.txt
cp .env.example .env            # rồi điền service URLs + AWS keys
```

### Biến môi trường (`.env`)

| Key | Default | Mô tả |
|---|---|---|
| `RAG_API_URL` | `http://localhost:8000` | RAG service endpoint (thường set `:8005`) |
| `SCANNER_API_URL` | `http://127.0.0.1:8000` | Prowler Scanner API |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `gemma3:4b` | LLM model name |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_DEFAULT_REGION` | — | AWS credentials |
| `MULTI_QUERY_MODE` | `false` | Bật multi-query RAG (Q1+Q2+Q3). Set `true` để dùng `/v1/retrieve/report_context` thay vì single-query. Xem [docs/rag-integration.md §8](docs/rag-integration.md). |
| `GROQ_API_KEY` | — | API key cho LLM judge (benchmark Day 2). Lấy tại [console.groq.com](https://console.groq.com). |

## Chạy hệ thống

Cần **3 service** chạy song song trước khi gọi pipeline. Mở 3 terminal:

### 1. Ollama (LLM)
```bash
ollama serve
```

### 2. RAG service (port 8005)
```bash
# Khuyến nghị: dùng start.py để có auto-reload khi dev
python RAG/start.py

# Hoặc không reload (production):
python RAG/start.py --no-reload
```
Lần đầu chạy cần build index:
```bash
python RAG/scripts/build_all.py
```

**Multi-query mode** (Q1+Q2+Q3 — xem [docs/rag-integration.md §8](docs/rag-integration.md)):
```bash
MULTI_QUERY_MODE=true python -m pdca.orchestrator
# hoặc thêm vào .env: MULTI_QUERY_MODE=true
```

### 3. Scanner API (port 8000)
```bash
# Windows cần UTF-8 cho log tiếng Việt
set PYTHONIOENCODING=utf-8
python -m uvicorn pdca.api_server:app --host 127.0.0.1 --port 8000
```

### 4. Chạy pipeline PDCA

**Interactive mode** (qua LangGraph resume-on-approval):
```bash
python -m pdca.orchestrator
```

**E2E auto-approve** (không cần tương tác):
```bash
python scripts/run_e2e_auto.py "scan all s3 buckets"
```

Output ở `data/artifacts/`:
- `final_report.{md,html,pdf}` — báo cáo cuối
- `pre_scan.json` / `post_scan.json` / `analysis_diff.json` — raw data
- `performance_metrics.json` — thời gian từng node
- `charts/*.png` — biểu đồ nhúng trong report

## Pipeline flow (LangGraph nodes)

```
environment → planning → scanning → monitoring → risk_eval
    → operational_planning → review_task (HITL) → execution
    → verification (rescan + analysis) → report
```

- `environment_agent`: lấy AWS context, kiểm tra RAG health
- `planning_agent`: phân tích request → chọn checks/groups (RAG-first, LLM-conditional)
- `scanner_agent`: trigger Prowler scan qua Scanner API
- `monitoring_agent`: poll job status đến khi xong
- `risk_evaluation_agent`: chấm severity, ưu tiên findings
- `remediate_planner_agent`: generate remediation tasks cho FAIL findings
- `execution_agent`: chạy remediation tool (có HITL approval gate)
- `rescan_agent`: chạy lại Prowler verify fix
- `analysis_agent`: diff pre/post, tính stats
- `report_agent`: render report (markdown + HTML + PDF, kèm maturity score)

## Testing

```bash
# Unit tests (không cần service)
python -m pytest tests/ --ignore=tests/rag_evaluation -q

# RAG integration tests (cần RAG service chạy)
python -m pytest tests/rag_evaluation/ -q

# RAG internal tests
python -m pytest RAG/tests/ -q
```

## Benchmarks

- **RAG retrieval** (`benchmarks/rag/`): đo nDCG, MRR, AP, precision, calibration
  ```bash
  python -m benchmarks.rag.benchmark_retrieval
  ```
- **LLM generation** (`benchmarks/llm_generation/`): đo faithfulness, grounding của Planning/Risk/Report agents
  ```bash
  python benchmarks/llm_generation/run_planning_benchmark.py --mode full
  python benchmarks/llm_generation/run_report_benchmark.py --mode full
  ```

## E2E testing với bucket mẫu

Script kiểm thử chuyên dụng `scripts/degrade_s3_for_e2e.py` flip 5-7 S3 checks
từ PASS sang FAIL (không expose data, có snapshot để revert):

```bash
# Degrade
python scripts/degrade_s3_for_e2e.py --bucket <bucket> --degrade --yes

# Chạy E2E
python scripts/run_e2e_auto.py "scan all s3 buckets"

# Revert
python scripts/degrade_s3_for_e2e.py --bucket <bucket> --revert
```

## Ghi chú refactor

Repo vừa refactor từ layout cũ (flat files ở root) sang package `pdca/`:
- `AgentState.py` → `pdca/state.py`
- `graph_orchestator.py` → `pdca/orchestrator.py` (fix typo)
- `agent_tools.py` → `pdca/tools.py`
- `agents/` → `pdca/agents/`
- `api_server.py`, `config.py`, `benchmark_report_models.py` → `pdca/`
- `benchmark_llm_gen/` → `benchmarks/llm_generation/`
- `RAG/data/benchmarks/` → `benchmarks/rag/`
- `data/` tách thành `raw/` (tracked), `samples/` (tracked), `artifacts/` (gitignored)

Dev workflow thay đổi: chạy module qua `python -m pdca.<module>` thay vì
`python <file>.py` trực tiếp.
