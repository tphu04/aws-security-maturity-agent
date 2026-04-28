# RAG Benchmark

Benchmark retrieval/context/ablation cho RAG service.

## Langfuse Guard

Tat ca benchmark entry point trong thu muc nay set `LANGFUSE_ENABLED=false`
bang `setdefault` theo Phase F.7 de bao ve quota Langfuse. Neu can debug mot
case benchmark tren Langfuse, export `LANGFUSE_ENABLED=true` truoc khi chay
script.
