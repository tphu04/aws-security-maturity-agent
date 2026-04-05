# Benchmark System - Tong quan

He thong co **3 loai benchmark** phuc vu 3 muc dich khac nhau.

## Ban do nhanh

```
Ban muon xem gi?
|
|-- "LLM danh gia severity co dung khong?"
|     |
|     +-> benchmark_llm_gen/
|          Doc: benchmark_outputs/gen_benchmark_dashboard.md
|          (So sanh llama3.2 vs qwen3:8b, w/RAG vs no-RAG)
|
|-- "RAG co retrieve dung document khong?"
|     |
|     +-> RAG/data/benchmarks/
|          Doc: benchmark_outputs/benchmark_dashboard.md
|          (Top-k accuracy, MRR, NDCG, latency)
|
|-- "Unit tests co pass khong?"
|     |
|     +-> tests/                    # Agent unit tests (pytest)
|     +-> tests/rag_evaluation/     # RAG quality integration tests
|     +-> RAG/tests/                # RAG module unit tests
```

---

## 1. LLM Generation Benchmark (`benchmark_llm_gen/`)

**Muc dich**: Danh gia chat luong output cua LLM khi phan loai severity.

| Cau hoi | File tra loi |
|---------|-------------|
| Ket qua tong hop la gi? | `benchmark_outputs/gen_benchmark_dashboard.md` |
| 30 test cases la gi? | `benchmark_gen_cases.json` |
| Nguong PASS/FAIL? | `release_criteria_gen.json` |
| Chay benchmark? | `python run_gen_benchmark.py --mode full` |
| Framework thiet ke? | `LLM_Generation_Evaluation_Report.md` |

Chi tiet: xem [benchmark_llm_gen/README.md](benchmark_llm_gen/README.md)

---

## 2. RAG Retrieval Benchmark (`RAG/data/benchmarks/`)

**Muc dich**: Danh gia chat luong retrieval pipeline (tim dung document, xep hang dung).

| Cau hoi | File tra loi |
|---------|-------------|
| Ket qua tong hop la gi? | `benchmark_outputs/benchmark_dashboard.md` |
| Test cases? | `benchmark_cases.json` |
| Nguong PASS/FAIL? | `release_criteria.json` |
| Chay benchmark? | `python -m RAG.scripts.run_benchmark` |
| So sanh 2 runs? | `python -m RAG.scripts.compare_benchmarks latest last` |
| A/B test reranker? | `python -m RAG.scripts.benchmark_reranker_ab` |

**Scripts lien quan** (trong `RAG/scripts/`):
- `run_benchmark.py` — Chay full benchmark (checks + maturity)
- `compare_benchmarks.py` — So sanh 2 runs, hien thi diff
- `benchmark_reranker_ab.py` — A/B test cross-encoder reranker

**Supplementary benchmarks** (trong `RAG/tests/`):
- `benchmark_s3_agent_readiness.py` — S3 context readiness cho agents
- `benchmark_topk_accuracy.py` — Top-k hit rate, MRR, MAP, latency

---

## 3. Unit & Integration Tests

### `tests/` (Agent-level)
| File | Test gi |
|------|---------|
| `test_risk_evaluation_agent_rs3.py` | RiskEvaluationAgent: orchestration, validation, RAG integration |
| `test_planning_agent_rs2.py` | PlanningAgent: fallback chain, confidence branching |
| `test_rag_client.py` | RAGClient: API calls, error handling |
| `test_shared_utils.py` | Shared utilities: extract_check_id, parse_llm_json |
| `test_rag_health_pipeline.py` | RAG health check flow |
| `test_endpoint_cleanup.py` | Endpoint cleanup logic |
| `test_orchestrator_rs4.py` | Graph orchestrator |

### `tests/rag_evaluation/` (RAG quality suite)
| File | Test gi |
|------|---------|
| `test_planning_rag_quality.py` | Planning agent + RAG: relevance, enrichment, reranking |
| `test_risk_rag_quality.py` | Risk agent + RAG: severity calibration, context usage |
| `test_rag_performance.py` | RAG performance: latency, throughput |
| `test_rag_fallback_degradation.py` | Graceful degradation khi RAG down |
| `run_evaluation.py` | Runner cho toan bo suite |

### `RAG/tests/` (RAG module-level)
| File | Test gi |
|------|---------|
| `test_evaluation_metrics.py` | Unit test cho tat ca metrics (MRR, NDCG, MAP...) |
| `test_rag_quality_for_agents.py` | RAG quality across all agent consumers |
| `test_context_build.py` | Context building logic |
| `test_rag_api.py` | RAG API endpoints |
| `test_rag_contract.py` | API contract compliance |
| `test_mapping_governance.py` | Mapping governance rules |
| `test_bundle_factory.py` | Bundle factory |
| `test_semantic_confidence.py` | Semantic confidence scoring |
| Nested: `test_retrieve_checks/`, `test_retrieve_maturity/`, `test_context_build/`, `test_planning_retrieval/` | Endpoint-specific test suites voi output snapshots |

---

## Quy uoc thu muc `_archive/`

Moi thu muc `benchmark_outputs/` va `inference_outputs/` co subfolder `_archive/` chua:
- Runs cu (truoc ngay hien tai)
- Runs trung gian (debug, thu nghiem)
- Mock data (test pipeline)

**Khong can xem `_archive/`** tru khi can trace lai lich su.
