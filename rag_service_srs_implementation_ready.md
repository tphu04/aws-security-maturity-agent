# RAG Service Software Requirements Specification (SRS)

## AWS Assessment Agent Platform

### Version: 1.0 (Implementation Ready)

### Date: 2026-03-15

------------------------------------------------------------------------

# 1. Purpose

This document defines the **Software Requirements Specification (SRS)**
for the Retrieval-Augmented Generation (RAG) Service used by the AWS
Assessment Agent platform.

The goal of this document is to provide a **developer-ready
implementation reference** that clearly describes:

-   system responsibilities
-   data structures
-   APIs
-   internal processing flow
-   build and runtime behavior

This document should allow engineers to implement the service **without
needing architectural clarification**.

------------------------------------------------------------------------

# 2. System Overview

The RAG Service provides **structured knowledge retrieval** for the AWS
Assessment Agent.

The service is responsible for retrieving knowledge related to:

-   AWS Security Maturity Model capabilities
-   Prowler security checks
-   mapping between checks and maturity capabilities

The RAG system **does not perform reasoning or generate reports**.

Instead, it provides **validated contextual knowledge** to the Analysis
Module.

------------------------------------------------------------------------

# 3. System Context

## External Systems

The RAG Service interacts with:

-   AWS Assessment Agent
-   LLM Service
-   Shared State Memory
-   Prowler Scan Results
-   Local Knowledge Corpus

## High Level Flow

User / Agent Request\
→ RAG Service\
→ Retrieval Engine\
→ Context Packaging\
→ Analysis Module\
→ Report Generation

------------------------------------------------------------------------

# 4. Functional Requirements

## FR1 --- Retrieve Maturity Knowledge

The system shall retrieve maturity model capabilities based on:

-   domain name
-   capability name
-   semantic query

Output must include:

-   capability metadata
-   summary
-   recommended practices

------------------------------------------------------------------------

## FR2 --- Retrieve Prowler Check Knowledge

The system shall retrieve Prowler check definitions based on:

-   natural language query
-   check_id
-   service filter

Output must include:

-   check title
-   description
-   risk
-   remediation

------------------------------------------------------------------------

## FR3 --- Resolve Check Mapping

The system shall map a `check_id` to:

-   maturity domain
-   capability

Mappings are maintained in an **internal mapping dataset**.

------------------------------------------------------------------------

## FR4 --- Build Analysis Context

The system shall generate a **combined context package** including:

-   check metadata
-   maturity capability context
-   mapping information

------------------------------------------------------------------------

# 5. Non Functional Requirements

## Performance

Target response times:

  Endpoint           Target
  ------------------ ------------
  Check Lookup       \< 500 ms
  Hybrid Retrieval   \< 1500 ms

------------------------------------------------------------------------

## Reliability

The system must:

-   never return silent failures
-   return explicit error states
-   degrade safely if retrieval backend fails

------------------------------------------------------------------------

## Maintainability

The implementation must:

-   use explicit schemas
-   maintain versioned indexes
-   support deterministic rebuilds

------------------------------------------------------------------------

# 6. Data Model

## Document Types

Supported document types:

-   maturity_capability
-   prowler_check
-   maturity_mapping

------------------------------------------------------------------------

## Maturity Capability Document

``` json
{
  "doc_type": "maturity_capability",
  "domain": "Identity and Access Management",
  "capability_id": "centralized_access_governance",
  "summary": "Centralize identity governance and access management."
}
```

------------------------------------------------------------------------

## Prowler Check Document

``` json
{
  "doc_type": "prowler_check",
  "check_id": "s3_account_level_public_access_blocks",
  "service": "s3",
  "severity": "high",
  "description": "Checks S3 account-level public access block settings."
}
```

------------------------------------------------------------------------

## Mapping Document

``` json
{
  "doc_type": "maturity_mapping",
  "check_id": "s3_account_level_public_access_blocks",
  "domain": "Data Protection",
  "capability_id": "public_data_exposure_prevention"
}
```

------------------------------------------------------------------------

# 7. Retrieval Architecture

The system uses **Hybrid Retrieval**.

Components:

-   Lexical Search (BM25)
-   Vector Search (Embeddings)
-   Result Merge Layer

Flow:

1.  Normalize query
2.  Detect query type
3.  Run lexical retrieval
4.  Run vector retrieval
5.  Merge results
6.  Apply filters
7.  Package response

------------------------------------------------------------------------

# 8. API Specification

## Search Maturity Knowledge

POST `/v1/retrieve/maturity`

Request:

``` json
{
  "query": "outbound traffic control",
  "top_k": 5
}
```

------------------------------------------------------------------------

## Search Prowler Checks

POST `/v1/retrieve/checks`

Request:

``` json
{
  "query": "S3 public access block",
  "service": "s3"
}
```

------------------------------------------------------------------------

## Resolve Mapping

POST `/v1/resolve/mapping`

Request:

``` json
{
  "check_id": "s3_account_level_public_access_blocks"
}
```

------------------------------------------------------------------------

## Build Context

POST `/v1/build/context`

Request:

``` json
{
  "finding": {
    "check_id": "s3_account_level_public_access_blocks",
    "service": "s3",
    "status": "FAIL"
  }
}
```

------------------------------------------------------------------------

# 9. Internal Modules

    rag_service/
    │
    ├── api
    │   ├── retrieve_routes.py
    │   ├── mapping_routes.py
    │   └── context_routes.py
    │
    ├── retrieval
    │   ├── router.py
    │   ├── lexical_retriever.py
    │   ├── vector_retriever.py
    │   ├── merge_strategy.py
    │   └── verifier.py
    │
    ├── ingestion
    │   ├── loaders.py
    │   ├── normalizers.py
    │   └── enrichers.py
    │
    ├── indexing
    │   ├── build_index.py
    │   ├── vector_store.py
    │   └── bm25_index.py
    │
    └── services
        ├── maturity_service.py
        ├── check_service.py
        └── context_service.py

------------------------------------------------------------------------

# 10. Build Pipeline

Offline pipeline:

1.  Load source datasets
2.  Normalize documents
3.  Enrich keywords and synonyms
4.  Generate embeddings
5.  Build BM25 index
6.  Build vector index
7.  Produce index manifest

------------------------------------------------------------------------

# 11. Observability

The system must log:

-   request_id
-   endpoint
-   query_type
-   latency
-   confidence level

Metrics:

-   request_count
-   error_count
-   latency_p95
-   no_result_count

------------------------------------------------------------------------

# 12. Security

RAG Service must:

-   run internally only
-   avoid storing secrets
-   sanitize logs

------------------------------------------------------------------------

# 13. Deployment

Recommended stack:

-   Python
-   FastAPI
-   Pydantic
-   FAISS or ChromaDB
-   Docker container

------------------------------------------------------------------------

# 14. Implementation Milestones

Phase 1:

-   schemas
-   corpus normalization
-   indexing pipeline

Phase 2:

-   retrieval APIs
-   hybrid search

Phase 3:

-   integration with analysis module

------------------------------------------------------------------------

# 15. Acceptance Criteria

The system is considered ready when:

-   check_id lookup accuracy = 100%
-   mapping resolution accuracy ≥ 95%
-   APIs return schema compliant responses
-   benchmark suite passes

------------------------------------------------------------------------

# End of SRS
