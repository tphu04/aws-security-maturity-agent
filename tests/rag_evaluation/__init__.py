"""
RAG Integration Quality Evaluation Tests
==========================================
Test suite danh gia chat luong tich hop RAG vao Planning Agent va Risk Evaluation Agent.

Modules:
    - conftest.py: Shared fixtures, mock data, helper functions
    - test_planning_rag_quality.py: Chat luong RAG cho PlanningAgent
    - test_risk_rag_quality.py: Chat luong RAG cho RiskEvaluationAgent
    - test_rag_fallback_degradation.py: Graceful degradation khi RAG khong kha dung
    - test_rag_performance.py: Performance benchmarks (latency, cache, batch)
    - run_evaluation.py: Runner script chay tat ca tests va tao bao cao
"""
