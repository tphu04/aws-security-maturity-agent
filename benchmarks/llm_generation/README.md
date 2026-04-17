# LLM Generation Benchmark

Benchmark danh gia chat luong **LLM output** cua Risk Evaluation Agent (severity classification).

## Cau truc thu muc

```
benchmark_llm_gen/
|
|-- Scripts (chay benchmark) ----------------------------------------
|   benchmark_generation.py        # Core engine: Load -> Inference -> Evaluate -> Aggregate
|   run_gen_benchmark.py           # CLI entry point (--mode full/inference-only/evaluate-only, --no-rag)
|   gen_metrics.py                 # 4 metrics: Structure, Faithfulness, Correctness, Completeness
|   collect_rag_snapshots.py       # Thu thap RAG context tu API, luu vao benchmark_gen_cases.json
|   generate_gen_dashboard.py      # Tao dashboard so sanh 4 configs (2 model x 2 RAG mode)
|
|-- Config ----------------------------------------------------------
|   benchmark_gen_cases.json       # 30 test cases (input finding + expected severity + RAG snapshot)
|   release_criteria_gen.json      # Nguong PASS/FAIL cho tung metric
|
|-- Docs ------------------------------------------------------------
|   LLM_Generation_Evaluation_Report.md   # Thiet ke framework danh gia
|   Implementation_Plan.md                # Ke hoach implement chi tiet
|
|-- benchmark_outputs/ ----------------------------------------------
|   gen_benchmark_dashboard.md     # ** DOC DAY ** Dashboard so sanh 4 configs
|   gen_benchmark_latest.json      # Ket qua run moi nhat
|   gen_benchmark_run_*_103853.json   # llama3.2 w/RAG   (final)
|   gen_benchmark_run_*_103854.json   # llama3.2 no-RAG  (final)
|   gen_benchmark_run_*_115443.json   # qwen3:8b no-RAG  (final)
|   gen_benchmark_run_*_122819.json   # qwen3:8b w/RAG   (final)
|   _archive/                      # Runs cu/trung gian (khong can xem)
|
|-- inference_outputs/ ----------------------------------------------
|   run_20260403_101355/           # llama3.2 w/RAG   inference (raw LLM outputs)
|   run_20260403_101900/           # llama3.2 no-RAG  inference
|   run_20260403_112326/           # qwen3:8b no-RAG  inference
|   run_20260403_120252/           # qwen3:8b w/RAG   inference
|   _archive/                      # Runs cu/mock (khong can xem)
```

## Cach chay

```bash
# 1. Thu thap RAG context moi nhat (can RAG server chay o localhost:8001)
python benchmark_llm_gen/collect_rag_snapshots.py

# 2. Chay benchmark day du (voi RAG)
python benchmark_llm_gen/run_gen_benchmark.py --mode full

# 3. Chay benchmark KHONG co RAG (ablation test)
python benchmark_llm_gen/run_gen_benchmark.py --mode full --no-rag

# 4. Chi evaluate tu inference co san
python benchmark_llm_gen/run_gen_benchmark.py --mode evaluate-only \
  --inference-dir benchmark_llm_gen/inference_outputs/run_20260403_101355

# 5. Tao dashboard so sanh
python benchmark_llm_gen/generate_gen_dashboard.py
```

## 4 Metrics danh gia

| Metric | Do gi | Cach tinh |
|--------|-------|-----------|
| **Structure** | LLM output co dung format JSON, schema, severity-score consistent | Deterministic rules |
| **Faithfulness** | Co hallucinate hoac tu mau thuan khong | Rule-based heuristic |
| **Correctness** | Severity co dung voi expected | Accuracy + QWK (Quadratic Weighted Kappa) |
| **Completeness** | Reasoning co de cap du evidence | Keyword matching |

## Mapping: inference run -> benchmark report

| Config | Inference run | Benchmark report |
|--------|--------------|------------------|
| llama3.2 w/RAG | run_20260403_101355 | gen_benchmark_run_20260403_103853.json |
| llama3.2 no-RAG | run_20260403_101900 | gen_benchmark_run_20260403_103854.json |
| qwen3:8b no-RAG | run_20260403_112326 | gen_benchmark_run_20260403_115443.json |
| qwen3:8b w/RAG | run_20260403_120252 | gen_benchmark_run_20260403_122819.json |
