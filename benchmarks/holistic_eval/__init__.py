"""Holistic end-to-end evaluation for the PDCA pipeline (D2).

Two analysis tracks reuse outputs from D1 (5 broad-scan runs):

    deliverable_quality.py  -- chấm chất lượng báo cáo cuối (4 metric)
    trajectory_eval.py      -- phân tích trace pipeline    (4 metric)

Both scripts read state from the chatbot API (cheap, structured) plus the
Langfuse export CSV at ``benchmarks/results/d1_20260505/``. No additional
GPU compute is required.
"""
