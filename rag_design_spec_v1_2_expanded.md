# RAG Design Specification
## AWS Assessment Agent - RAG Service

**Version:** 1.2  
**Status:** Expanded Draft for Review  
**Owner:** RAG / Assessment Platform  
**Last Updated:** 2026-03-15

---

# 1. Document Purpose

This document defines the official design specification for the Retrieval-Augmented Generation (RAG) subsystem used by the AWS Assessment Agent platform.

The main purpose of this specification is not only to define the technical contract of the RAG service, but also to make the service easy to implement, easy to review, and easy to consume later by analysis and reporting modules.

This specification therefore serves three roles at the same time:

1. **Architecture specification** — defines what the RAG subsystem is, what it owns, and what it must not do.
2. **Implementation guide** — gives developers enough detail to implement the service without needing to infer core behavior.
3. **Reporting support contract** — ensures the outputs of RAG are structured so downstream modules can generate explainable analysis and readable reports.

## 1.1 Intended Audience

This document is intended to be the primary technical reference for:
- backend developers implementing the RAG service
- engineers integrating agent modules with the RAG service
- reviewers validating architecture and scope
- maintainers evolving the service in later phases
- analysis/report engineers who need to understand what retrieval outputs mean and how they should be interpreted

## 1.2 What This Document Should Enable

After reading this specification, a developer should be able to:
- understand the purpose and limits of the RAG subsystem
- prepare the source corpus in the expected format
- implement the ingestion and indexing pipeline
- implement the core retrieval endpoints
- understand confidence, verification, and fallback behavior
- understand how RAG output should be consumed by analysis and reporting modules

After reading this specification, a reviewer should be able to:
- verify whether the design is sufficiently bounded for v1
- identify risks in retrieval correctness, traceability, and maintainability
- validate whether the API and schema choices are suitable for downstream integration

---

# 2. Scope

## 2.1 In-Scope for RAG v1

RAG v1 is designed to support the AWS Assessment Agent system by providing structured retrieval over:
- AWS Security Maturity Model knowledge
- Prowler check metadata and finding-related context
- manual mapping between Prowler checks and AWS maturity capabilities

RAG v1 will support the following primary use cases:

1. Retrieve maturity knowledge by concept, domain, or capability
2. Retrieve Prowler check knowledge by natural language or check ID
3. Resolve mapping from `check_id` to maturity domain/capability
4. Build analysis-ready context for downstream agent or LLM modules
5. Return structured context with confidence and metadata
6. Support explainable downstream reporting by preserving source attribution and rationale metadata

## 2.2 Out-of-Scope for RAG v1

The following are explicitly out of scope for this version:
- autonomous agentic RAG planning
- graph RAG / knowledge graph retrieval
- multi-hop reasoning workflows
- full internet/web retrieval during runtime
- advanced learning-to-rank training
- online incremental ingestion from arbitrary untrusted sources
- generating final business report text inside the RAG service
- making assessment decisions directly inside RAG
- remediation execution planning inside RAG
- distributed large-scale multi-tenant deployment

## 2.3 Practical Interpretation of Scope

The RAG service is a **knowledge retrieval component**, not the full intelligence layer of the system.

That means:
- it is responsible for finding and packaging the right context
- it is not responsible for deciding whether an environment is compliant, mature, or acceptable
- it is not responsible for writing the final executive wording of a report
- it should remain deterministic and inspectable enough that engineers can debug retrieval mistakes

This boundary is important because many problems that look like “RAG issues” are actually analysis or reporting issues. The service should make those boundaries clear.

---

# 3. System Context

## 3.1 Position in Overall Architecture

RAG is a standalone service that is called by internal modules of the AWS Assessment Agent system.

### Existing System Components
- User Interface
- AWS Assessment Agent
  - Environment Module
  - Planning Module
  - Monitoring Module
  - Scanning Module
  - Risk Evaluation Module
  - Operational Planner Module
  - Review Tasks (HITL)
  - Execution Module
  - Rescan Module
  - Analysis Module
  - Report Module
- Shared State Memory
- Infrastructure
  - LLM Service
  - External Tools
  - Target Cloud
  - Storage

### RAG-Specific Components to Add
- Semantic Router
- RAG Engine
- Verification Layer
- Vector Database / Retrieval Indexes
- Embedding / Chunking / Knowledge Preparation Pipeline

## 3.2 Boundary of Responsibility

### RAG Service Responsibilities
- retrieve relevant maturity knowledge
- retrieve relevant Prowler check knowledge
- resolve mappings from checks to maturity capabilities
- package context for downstream analysis
- return confidence and retrieval metadata
- expose stable APIs for internal service-to-service use

### RAG Service Must Not
- produce final maturity assessment decision as source of truth
- produce final user-facing report as authoritative output
- mutate core agent state directly
- invoke cloud remediation tools
- perform scan orchestration
- act as a general-purpose chatbot

### LLM / Analysis Module Responsibilities
- reason over findings and retrieved context
- produce structured maturity assessment output
- generate human-readable explanations and reports
- decide final interpretation of findings using provided context

## 3.3 High-Level Interaction Model

At a high level, the flow should look like this:

1. A caller sends a request to RAG.
2. The semantic router classifies the request.
3. RAG performs exact lookup, lexical retrieval, vector retrieval, or a combination.
4. RAG verifies and packages the results.
5. The caller consumes structured output.
6. The Analysis Module reasons over that output.
7. The Report Module later transforms analysis output into human-readable report content.

This means the RAG layer should optimize for:
- finding the right supporting knowledge
- structuring it in a stable format
- preserving enough metadata for explanation and review

---

# 4. Design Principles

The following principles guide all implementation decisions for RAG v1:

1. **Retrieval-first**  
   The system must prioritize correct retrieval and context packaging before any advanced generation features.

2. **Structured over free-form**  
   RAG should return structured JSON with metadata, confidence, and typed content rather than only text snippets.

3. **Small, stable, and reviewable**  
   Phase 1 should remain bounded and easy to inspect, test, and iterate on.

4. **Source-aware**  
   All retrieved knowledge must preserve source attribution and source type.

5. **Deterministic where possible**  
   Query normalization, filtering, mapping lookup, and fallback policies should prefer deterministic logic over hidden model behavior.

6. **Human-review compatible**  
   The service must support low-confidence outputs and explicit review workflows.

7. **Versioned and reproducible**  
   Corpus builds, embeddings, and index versions must be tracked.

8. **Report-friendly**  
   The outputs should be easy for downstream analysis and report generation to explain. Fields should not be optimized only for retrieval internals; they should also be meaningful to later consumers.

## 4.1 Why These Principles Matter

These principles are important because RAG systems often fail in one of four ways:
- they retrieve the wrong thing
- they retrieve the right thing but cannot explain why
- they retrieve useful text but do not structure it for downstream systems
- they become too “smart” too early and become difficult to debug

This design intentionally avoids these traps by preferring explicit schemas, explicit mappings, and conservative confidence handling.

---

# 5. Primary Use Cases

## 5.1 Use Case A: Maturity Knowledge Retrieval

### Goal
Retrieve relevant AWS Security Maturity Model knowledge based on a concept, domain, or capability.

### Example Inputs
- `identity governance`
- `network traffic control`
- `outbound traffic restrictions`
- `capability related to centralized logging`

### Output
Structured maturity chunks including:
- domain
- capability
- summary
- practices
- source metadata
- confidence

### Why It Exists
This use case supports analysis modules that need to understand what “good” or “mature” security practice looks like in the context of AWS security capabilities.

### Downstream Value
This output helps the Analysis Module:
- explain why a finding matters in maturity terms
- align technical findings with capability-level assessment
- support report sections such as “Affected Capability”, “Expected Practice”, and “Assessment Rationale”

## 5.2 Use Case B: Prowler Check Retrieval

### Goal
Retrieve relevant Prowler check knowledge from natural language, technical keywords, or exact check IDs.

### Example Inputs
- `S3 public access block`
- `check for CloudTrail multi-region`
- `s3_account_level_public_access_blocks`
- `encryption check for EBS`

### Output
Structured check documents including:
- check_id
- title
- service
- severity
- description
- risk
- remediation
- score
- confidence

### Why It Exists
This use case supports both technical interpretation and user-intent routing. A user or planning module may not know the exact check ID, but still needs the correct check retrieved.

### Downstream Value
This output helps:
- the Planning Module choose the correct scan target or check set
- the Analysis Module explain what a check means technically
- the Report Module build sections like “Technical Description”, “Risk”, and “Recommended Control Direction”

## 5.3 Use Case C: Mapping Resolution

### Goal
Resolve which maturity domain and capability a Prowler check belongs to.

### Example Inputs
- `check_id`
- finding metadata containing `check_id`, `service`, and optional description

### Output
Structured mapping result including:
- domain
- capability
- rationale
- mapping_confidence
- source_of_mapping
- review flags

### Why It Exists
Technical findings and maturity capabilities are not the same thing. A separate mapping layer is needed so the system does not assume that every technical control maps directly and unambiguously to a maturity concept.

### Downstream Value
This mapping is what allows later report content to say things like:
- this failed technical control affects capability X
- this issue weakens maturity domain Y
- this finding contributes to evidence for or against capability Z

## 5.4 Use Case D: Analysis Context Packaging

### Goal
Build a combined context package for downstream analysis.

### Example Inputs
- check_id
- finding metadata
- optional query
- optional service/domain hints

### Output
Context package combining:
- check context
- maturity context
- mapping context
- metadata
- confidence
- review recommendation

### Why It Exists
The analysis layer should not need to manually call multiple retrieval paths and stitch results together itself for common workflows.

### Downstream Value
This use case directly supports:
- finding-level analysis
- capability-level scoring logic
- evidence packaging for reports
- reviewer workflows when confidence is not high

## 5.5 Use Case E: Report Support Context

### Goal
Provide report-friendly structured supporting context without letting RAG generate the final report text.

### Output Characteristics
The returned context should be usable for report generation fields such as:
- technical issue summary
- affected service
- affected maturity capability
- why the control matters
- expected practice
- remediation direction
- confidence and review status

### Why It Exists
Later report-writing modules need clear, stable, and attributable supporting inputs. This is easier when RAG returns structured evidence instead of loose text snippets.

---

# 6. Source of Truth and Corpus Definition

## 6.1 Official Knowledge Sources

RAG v1 uses the following official sources:

### Source A: AWS Security Maturity Model
**Purpose:**
- authoritative maturity knowledge
- capability and domain definitions
- maturity best-practice context

**Role:**
- source of truth for maturity reasoning context

**Implementation Note:**
For v1, the ingestion source will be a cleaned Markdown representation plus normalized JSON extraction per capability. The original official source remains the real authority, but the normalized internal snapshot is the runtime corpus input.

### Source B: Prowler Check Metadata and Finding Definitions
**Purpose:**
- authoritative technical check information
- check title, service, severity, risk, remediation
- direct technical interpretation of findings

**Role:**
- source of truth for technical detection/check context

**Implementation Note:**
For v1, the ingestion source will be an internal reviewed JSON snapshot generated from the selected Prowler metadata export.

### Source C: Internal Manual Mapping Layer
**Purpose:**
- explicit mapping from Prowler checks to maturity domains/capabilities
- preserve domain review decisions and rationale

**Role:**
- source of truth for maturity mapping in v1

**Implementation Note:**
This is a critical internal artifact, not a secondary convenience file. The mapping layer is part of the formal knowledge model and must be versioned and reviewed.

## 6.2 Corpus Categories

The corpus is divided into the following logical groups:

1. `maturity_knowledge`
2. `prowler_check_knowledge`
3. `mapping_knowledge`

## 6.3 Allowed Source Formats for v1

Allowed formats:
- JSON
- YAML
- CSV
- cleaned markdown/plain text extracted from docs

Not preferred for direct runtime ingestion:
- raw HTML pages
- arbitrary PDFs
- dynamically scraped pages without preprocessing

## 6.4 Corpus Quality Rules

Before a source can enter the runtime corpus, it should satisfy these baseline rules:
- the source must be identifiable and versioned
- the source must have an owner
- the transformation process must be reproducible
- the resulting normalized records must pass schema validation
- duplicate or conflicting records must be resolved before index build

## 6.5 Source Ownership and Review

For v1, ownership is defined as follows:
- maturity corpus snapshot: Assessment Platform team, reviewed by domain/security reviewer
- Prowler metadata snapshot: Platform implementation owner, reviewed for completeness and consistency
- manual mappings: Assessment Platform team plus domain/security reviewer

This review requirement exists because incorrect mappings can create misleading reports even when retrieval works correctly.

---

# 7. Knowledge Model

## 7.1 Document Types

RAG v1 supports the following document types:
- `maturity_capability`
- `prowler_check`
- `maturity_mapping`

## 7.2 Common Metadata Fields

All indexed documents must include:
- `doc_id`
- `doc_type`
- `source_name`
- `source_type`
- `source_uri`
- `version`
- `created_at`
- `updated_at`
- `language`
- `tags`
- `index_version`

## 7.3 Metadata Semantics

The purpose of common metadata is not only bookkeeping. These fields have specific downstream value:

- `doc_id`: stable internal identity for deduplication and traceability
- `doc_type`: determines which retrieval logic and schema apply
- `source_name`: human-readable source identity
- `source_type`: explains the trust level and nature of the source
- `source_uri`: points to the internal source reference or canonical snapshot location
- `version`: content version of the normalized record or source snapshot
- `created_at` / `updated_at`: record lifecycle metadata
- `language`: useful for bilingual support and filtering
- `tags`: lightweight retrieval hints and categorization
- `index_version`: allows exact trace-back to the retrieval build used

## 7.4 Maturity Capability Document Schema

```json
{
  "doc_id": "maturity:identity-and-access-management:centralized-access-governance",
  "doc_type": "maturity_capability",
  "domain": "Identity and Access Management",
  "capability_id": "centralized_access_governance",
  "capability_name": "Centralized Access Governance",
  "stage": "Foundational",
  "summary": "Centralize and standardize identity governance and access management practices.",
  "recommended_practices": [
    "Use centrally managed identities",
    "Apply least privilege",
    "Review access regularly"
  ],
  "keywords": [
    "identity governance",
    "iam",
    "access control",
    "least privilege"
  ],
  "source_name": "aws_security_maturity_model",
  "source_type": "official_doc",
  "source_uri": "internal://sources/aws_security_maturity_model/v2026-03-15",
  "language": "en",
  "version": "1.0",
  "index_version": "rag-v1"
}
```

### Required Interpretation
A `maturity_capability` document represents a retrievable capability-level unit of maturity knowledge. It should be small enough to retrieve cleanly, but rich enough to support later explanation.

### Authoring Guidance
A maturity capability record should be understandable even when retrieved in isolation. That means its `summary` and `recommended_practices` should not rely heavily on surrounding page context.

## 7.5 Prowler Check Document Schema

```json
{
  "doc_id": "check:s3_account_level_public_access_blocks",
  "doc_type": "prowler_check",
  "check_id": "s3_account_level_public_access_blocks",
  "provider": "aws",
  "service": "s3",
  "title": "Ensure S3 account-level public access blocks are enabled",
  "severity": "high",
  "description": "Checks whether account-level public access block settings are enabled for Amazon S3.",
  "risk": "If disabled, S3 resources may be exposed publicly by mistake.",
  "remediation": "Enable S3 Block Public Access at the account level.",
  "resource_type": "account",
  "keywords": [
    "s3",
    "public access",
    "block public access",
    "account level"
  ],
  "synonyms": [
    "s3 public access block",
    "block public s3",
    "chặn public s3",
    "truy cập công khai s3"
  ],
  "source_name": "prowler_checks",
  "source_type": "official_check_metadata",
  "source_uri": "internal://sources/prowler_checks_snapshot/v2026-03-15",
  "language": "en",
  "version": "1.0",
  "index_version": "rag-v1"
}
```

### Required Interpretation
A `prowler_check` record is the primary technical retrieval unit. It should be retrievable by exact ID, by service-specific technical terms, and by user-facing natural language.

### Authoring Guidance
The `description`, `risk`, and `remediation` fields should remain close to authoritative wording. These fields later support report explanations, so they should not be casually paraphrased during normalization.

## 7.6 Mapping Document Schema

```json
{
  "doc_id": "mapping:s3_account_level_public_access_blocks",
  "doc_type": "maturity_mapping",
  "check_id": "s3_account_level_public_access_blocks",
  "provider": "aws",
  "service": "s3",
  "domain": "Data Protection",
  "capability_id": "public_data_exposure_prevention",
  "capability_name": "Public Data Exposure Prevention",
  "mapping_confidence": "high",
  "mapping_reason": "This check directly supports prevention of unintended public exposure of data resources.",
  "review_status": "reviewed",
  "reviewed_by": "platform-team",
  "source_name": "manual_mappings",
  "source_type": "reviewed_internal_mapping",
  "source_uri": "internal://sources/manual_mappings/v1",
  "version": "1.0",
  "index_version": "rag-v1"
}
```

### Required Interpretation
A mapping record is an explicit, reviewed statement that a specific technical check contributes evidence for a specific maturity capability.

### Important Constraint
A mapping record does **not** mean the check alone proves full maturity or immaturity of the capability. It only means the check is relevant evidence for that capability.

## 7.7 Additional Recommended Fields for v1.2

To make implementation and report generation easier, the following optional fields are recommended even if not all are strictly required in the first code version:

### For `maturity_capability`
- `domain_id`
- `evidence_examples`
- `control_objective`
- `report_summary`

### For `prowler_check`
- `compliance_refs`
- `default_enabled` or equivalent metadata if available
- `report_summary`
- `technical_category`

### For `maturity_mapping`
- `mapping_type` (direct, supporting, partial)
- `assessment_weight_hint`
- `report_note`

These fields are not mandatory blockers for v1 implementation, but they are recommended because they reduce later refactoring when the reporting layer matures.

---

# 8. Storage and Indexing Model

## 8.1 Logical Storage Components

RAG v1 should separate data into:
- normalized document storage
- lexical retrieval index
- vector retrieval index
- mapping storage
- build metadata storage

## 8.2 Recommended Minimal Storage Choice

For v1, the recommended practical setup is:
- normalized docs: JSON files
- lexical search: BM25 over normalized text fields
- vector store: ChromaDB
- mapping records: JSON or YAML file
- build metadata: JSON manifest

## 8.3 Why This Minimal Choice Is Recommended

This stack is intentionally simple because it provides:
- low setup cost
- local inspectability
- easy rebuilds
- low operational complexity
- easy debugging during development

For v1, developer productivity and correctness are more important than scale optimization.

## 8.4 Build Manifest Schema

```json
{
  "index_version": "rag-v1-2026-03-15",
  "embedding_model": "intfloat/multilingual-e5-base",
  "build_timestamp": "2026-03-15T10:00:00Z",
  "sources": {
    "maturity_docs": "aws_security_maturity_model_v2026-03-15",
    "prowler_checks": "prowler_checks_snapshot_v2026-03-15",
    "mappings": "manual_mappings_v1"
  },
  "doc_counts": {
    "maturity_capability": 0,
    "prowler_check": 0,
    "maturity_mapping": 0
  }
}
```

## 8.5 Build Reproducibility Requirements

A build should be reproducible from the manifest and source snapshots. In practice, this means:
- source snapshot IDs must be fixed
- normalization rules must be deterministic
- embedding model version must be fixed
- the exact code used to build the index should be tied to the service version or commit reference

This requirement matters for debugging. If a future report is questioned, the team must be able to identify exactly which knowledge build was used.

---

# 9. Ingestion and Normalization Pipeline

## 9.1 Pipeline Overview

The indexing pipeline for RAG v1 consists of:
- source ingestion
- cleaning and normalization
- document transformation
- keyword and synonym enrichment
- chunking where applicable
- embedding generation
- lexical index build
- vector index build
- manifest generation
- validation checks

## 9.2 Source Ingestion

### Maturity Model Ingestion

**Input:**
- cleaned content derived from official AWS Security Maturity Model pages

**Expected output:**
- one or more `maturity_capability` documents per capability or section

### Prowler Metadata Ingestion

**Input:**
- check metadata exports
- official check list / internal snapshot

**Expected output:**
- one `prowler_check` document per check

### Mapping Ingestion

**Input:**
- reviewed mapping file

**Expected output:**
- one `maturity_mapping` record per mapped check

## 9.3 Normalization Rules

The following normalization rules must be applied:
- trim whitespace
- normalize unicode
- lower-case retrieval support fields
- preserve original title case in display fields
- normalize service names to canonical forms
- normalize provider to canonical values
- deduplicate keywords
- remove boilerplate navigation text from maturity docs
- preserve authoritative wording in summary/risk/remediation fields

## 9.4 Recommended Canonicalization Rules

To reduce inconsistencies across retrieval and reporting, the following canonical forms are recommended:
- provider: `aws`
- service values: lowercase canonical service identifiers such as `s3`, `iam`, `ec2`, `cloudtrail`
- severities: normalized to one agreed scale such as `critical`, `high`, `medium`, `low`, `informational`
- booleans and enum-like flags should be normalized before indexing, not during query time

## 9.5 Synonym Enrichment

Synonym enrichment should be implemented conservatively.

### Allowed Sources of Synonyms
- manually curated domain dictionary
- deterministic rule-based variants
- reviewed bilingual glossary

### Not Recommended in v1
- uncontrolled LLM-generated synonym expansion without review

### Example Dictionary

```json
{
  "public access": [
    "public exposure",
    "publicly accessible",
    "truy cập công khai",
    "công khai"
  ],
  "encryption": [
    "mã hóa",
    "encrypted",
    "at-rest encryption"
  ],
  "logging": [
    "ghi log",
    "audit logging",
    "centralized logs"
  ]
}
```

## 9.6 Chunking Strategy

### Maturity Documents
Chunk by semantic section or capability.  
Do not chunk purely by character count unless absolutely necessary.

### Prowler Checks
Each check is usually one standalone document and should not be further chunked in v1.

### Mapping Documents
No chunking. These remain structured records.

## 9.7 Validation Checks During Build

Before an index build is accepted, the pipeline should validate:
- all records pass schema validation
- all `check_id` values are unique
- all mapping records reference existing `check_id` values
- all mappings reference valid capability IDs
- required metadata fields are present
- lexical and vector indexes contain the expected document counts
- manifest counts match actual built artifacts

## 9.8 Failure Policy During Build

If a build contains fatal validation issues, the build should fail explicitly. A partially corrupted build should not be promoted silently.

Examples of fatal build issues:
- invalid schema in normalized records
- missing required source snapshot
- mapping references unknown capability
- index artifact count mismatch

---

# 10. Retrieval Architecture

## 10.1 Retrieval Strategy

RAG v1 uses a hybrid retrieval strategy:
- lexical retrieval for exact technical terms and IDs
- vector retrieval for semantic matching
- merge results
- optionally rerank top candidates
- package the final context

## 10.2 Retrieval Pipeline

1. receive request
2. normalize query
3. infer query type
4. apply filters
5. run lexical retrieval
6. run vector retrieval
7. merge candidates
8. optionally rerank
9. verify basic consistency
10. package response
11. return structured result

## 10.3 Query Types

The semantic router must classify requests into one of the following types:
- `maturity_search`
- `check_search`
- `mapping_resolution`
- `context_build`

## 10.4 Filter Model

Supported filters in v1:
- `doc_type`
- `provider`
- `service`
- `domain`
- `capability_id`
- `check_id`

## 10.5 Lexical Retrieval

Lexical retrieval is required for:
- check_id matching
- service names
- exact technical terms
- domain/capability names
- known keywords

Input text for lexical indexing should be formed from:
- titles
- descriptions
- keywords
- synonyms
- risk/remediation summaries
- capability names and summaries

### Practical Rule
If the query looks like a check ID, lexical exact lookup should run first before broader search.

## 10.6 Vector Retrieval

Vector retrieval is required for:
- concept-based maturity search
- natural language search over checks
- bilingual or paraphrased queries
- low-exactness semantic retrieval

Embedding text should include:
- primary title/name
- summary/description
- keywords
- synonyms
- short supporting context

## 10.7 Merge Strategy

Recommended merge strategy for v1:
- retrieve top N from lexical
- retrieve top N from vector
- merge using Reciprocal Rank Fusion (RRF) or a simple weighted rank merge
- keep merged top K for reranking or response

## 10.8 Reranking

Reranking is optional in the earliest implementation, but the interface should support it.

If reranking is used:
- rerank only a small top candidate set
- preserve raw retrieval scores
- do not hide original retrieval evidence

## 10.9 Retrieval Result Semantics

A retrieval score should be treated as a retrieval relevance indicator, not as business confidence by itself.

This matters because:
- a high lexical score does not automatically mean the result is the correct maturity mapping
- a good semantic score does not automatically mean the service should claim high confidence
- business confidence must consider filters, exactness, reviewed mappings, and ambiguity

---

# 11. Semantic Router

## 11.1 Purpose

The semantic router determines which retrieval path the request should follow.

## 11.2 Responsibilities

The router must infer:
- query type
- target document type
- optional service/provider
- optional domain/capability intent
- whether exact ID lookup is likely

## 11.3 Router Inputs

Possible inputs:
- raw query text
- explicit request type
- `check_id` if already provided
- service hint from caller
- domain hint from caller

## 11.4 Router Outputs

```json
{
  "query_type": "check_search",
  "doc_types": ["prowler_check"],
  "provider": "aws",
  "service": "s3",
  "requires_exact_lookup": false
}
```

## 11.5 Router Implementation Guidance

For v1, the router should be primarily rule-based:
- exact pattern detection for `check_id`
- keyword detection for domain and service
- explicit request type from caller takes precedence
- fallback to semantic search mode when no exact route is identified

Do not make router logic fully model-dependent in v1.

## 11.6 Router Design Notes for Developers

The router should be explainable. A developer should be able to log and inspect:
- why the request was classified a certain way
- which service hint was inferred
- whether exact lookup was attempted
- whether the system fell back to semantic search

This is especially important for debugging planning failures where the user asks for a human-language concept and the system must still retrieve the correct technical checks.

---

# 12. Verification Layer

## 12.1 Purpose

The verification layer performs lightweight validation of retrieved results before returning them.

## 12.2 Verification Checks in v1

The service should verify:
- exact `check_id` exists when exact lookup is requested
- top result service matches requested service if service filter was applied
- mapping result exists and is reviewed when high-confidence mapping is claimed
- returned result type matches requested query type
- duplicate results are removed
- empty results are handled explicitly

## 12.3 Verification Output

```json
{
  "verified": true,
  "issues": [],
  "review_recommended": false
}
```

Or:

```json
{
  "verified": false,
  "issues": [
    "low_confidence_mapping",
    "service_mismatch_detected"
  ],
  "review_recommended": true
}
```

## 12.4 Verification Philosophy

The verification layer should remain simple. It is not a second reasoning engine. Its purpose is to catch obvious retrieval contract violations and ambiguity indicators.

Examples:
- if the caller requested service `s3` and the top result is an `iam` check, the service should not quietly proceed as if that is fine
- if a mapping is missing, the service should not fabricate one from semantic similarity alone

---

# 13. Confidence Model

## 13.1 Confidence Levels

RAG v1 uses qualitative confidence levels:
- `high`
- `medium`
- `low`

## 13.2 Confidence Determination Inputs

Confidence may consider:
- presence of exact ID match
- consistency between lexical and vector top results
- score margin between top result and next result
- existence of reviewed mapping
- filter alignment
- query ambiguity

## 13.3 Confidence Rules

### High
- exact match, or
- strong lexical + semantic agreement, and
- filter-aligned result, and
- mapping reviewed if applicable

### Medium
- relevant results exist but multiple candidates compete, or
- semantic match is good but exactness is lower

### Low
- weak scores
- no strong agreement
- ambiguous intent
- missing reviewed mapping
- service/domain mismatch risk

## 13.4 Review Recommendation

Any low-confidence result must set:

```json
{
  "review_recommended": true
}
```

## 13.5 Important Interpretation Rule

Confidence in this service means **retrieval confidence**, not final assessment confidence.

For example:
- RAG may be highly confident that a finding maps to a capability
- the Analysis Module may still be uncertain how much that finding affects overall maturity

These two forms of confidence must not be mixed.

---

# 14. Fallback Policy

## 14.1 General Policy

The service must never silently fail by returning empty structured meaning without explanation.

## 14.2 Fallback Behaviors

### Exact ID Not Found
Return:
- empty results
- `confidence = low`
- explicit issue = `check_id_not_found`

### Low-Confidence Search
Return:
- top candidate list
- `confidence = low`
- `review_recommended = true`

### Mapping Missing
Return:
- check context if found
- no mapping or partial mapping response
- issue = `mapping_missing`
- review recommended

### Service Ambiguity
Return:
- candidate results grouped or filtered conservatively
- issue = `service_ambiguous`

## 14.3 Fallback Design Goal

A caller should always be able to distinguish between:
- nothing was found
- something relevant was found but confidence is low
- the technical check was found but no reviewed mapping exists
- retrieval succeeded but review is recommended

This distinction is important for both workflow automation and later human review.

---

# 15. API Specification

## 15.1 API Style

- internal service-to-service JSON API
- REST over HTTP
- synchronous request/response for v1

## 15.2 Common Response Envelope

```json
{
  "request_id": "uuid",
  "status": "success",
  "data": {},
  "meta": {
    "index_version": "rag-v1-2026-03-15",
    "confidence": "high",
    "review_recommended": false
  },
  "errors": []
}
```

## 15.3 API Design Rules

All endpoints should follow these rules:
- request and response schemas must be explicit and validated
- response envelopes should remain consistent across endpoints
- `request_id` must be generated for traceability
- `meta` should always exist even in error responses
- `errors` should be structured and machine-readable

## 15.4 Endpoint: Search Maturity Knowledge

### Route
`POST /v1/retrieve/maturity`

### Request

```json
{
  "query": "outbound traffic control",
  "domain": null,
  "capability_id": null,
  "top_k": 5,
  "debug": false
}
```

### Response

```json
{
  "request_id": "uuid",
  "status": "success",
  "data": {
    "results": [
      {
        "doc_id": "maturity:network-security:outbound-traffic-control",
        "domain": "Network Security",
        "capability_id": "outbound_traffic_control",
        "capability_name": "Outbound Traffic Control",
        "summary": "Control and restrict outbound traffic paths.",
        "recommended_practices": [
          "Define egress boundaries",
          "Monitor outbound traffic"
        ],
        "score": 0.91
      }
    ]
  },
  "meta": {
    "index_version": "rag-v1-2026-03-15",
    "confidence": "high",
    "review_recommended": false
  },
  "errors": []
}
```

### Notes for Consumers
Use this endpoint when the caller needs capability-level best-practice context, not when it already has a check ID and needs technical interpretation.

## 15.5 Endpoint: Search Prowler Checks

### Route
`POST /v1/retrieve/checks`

### Request

```json
{
  "query": "kiểm tra public access block của S3",
  "check_id": null,
  "provider": "aws",
  "service": "s3",
  "top_k": 5,
  "debug": true
}
```

### Response

```json
{
  "request_id": "uuid",
  "status": "success",
  "data": {
    "normalized_query": "s3 public access block",
    "results": [
      {
        "doc_id": "check:s3_account_level_public_access_blocks",
        "check_id": "s3_account_level_public_access_blocks",
        "service": "s3",
        "title": "Ensure S3 account-level public access blocks are enabled",
        "severity": "high",
        "description": "Checks whether account-level public access block settings are enabled.",
        "risk": "If disabled, S3 resources may be exposed publicly.",
        "remediation": "Enable account-level block public access.",
        "score": 0.94,
        "rank": 1
      },
      {
        "doc_id": "check:s3_access_point_public_access_block",
        "check_id": "s3_access_point_public_access_block",
        "service": "s3",
        "title": "Ensure S3 access point public access blocks are enabled",
        "severity": "high",
        "description": "Checks access point public access block settings.",
        "risk": "Access points may allow unintended exposure.",
        "remediation": "Enable block public access for access points.",
        "score": 0.89,
        "rank": 2
      }
    ]
  },
  "meta": {
    "index_version": "rag-v1-2026-03-15",
    "confidence": "high",
    "review_recommended": false
  },
  "errors": []
}
```

### Notes for Consumers
This endpoint is the main entry point for planning and natural-language technical retrieval.

## 15.6 Endpoint: Resolve Mapping

### Route
`POST /v1/resolve/mapping`

### Request

```json
{
  "check_id": "s3_account_level_public_access_blocks",
  "provider": "aws",
  "service": "s3"
}
```

### Response

```json
{
  "request_id": "uuid",
  "status": "success",
  "data": {
    "mapping": {
      "check_id": "s3_account_level_public_access_blocks",
      "domain": "Data Protection",
      "capability_id": "public_data_exposure_prevention",
      "capability_name": "Public Data Exposure Prevention",
      "mapping_confidence": "high",
      "mapping_reason": "The check directly supports prevention of public data exposure.",
      "review_status": "reviewed"
    }
  },
  "meta": {
    "index_version": "rag-v1-2026-03-15",
    "confidence": "high",
    "review_recommended": false
  },
  "errors": []
}
```

### Notes for Consumers
Use this endpoint when technical context is already known and the caller specifically needs capability alignment.

## 15.7 Endpoint: Build Analysis Context

### Route
`POST /v1/build/context`

### Request

```json
{
  "finding": {
    "check_id": "s3_account_level_public_access_blocks",
    "service": "s3",
    "status": "FAIL",
    "severity": "high"
  },
  "include_check_context": true,
  "include_maturity_context": true,
  "include_mapping_context": true,
  "top_k": 3
}
```

### Response

```json
{
  "request_id": "uuid",
  "status": "success",
  "data": {
    "check_context": {
      "check_id": "s3_account_level_public_access_blocks",
      "title": "Ensure S3 account-level public access blocks are enabled",
      "description": "Checks whether account-level public access block settings are enabled.",
      "risk": "If disabled, S3 resources may be exposed publicly.",
      "remediation": "Enable account-level block public access."
    },
    "mapping_context": {
      "domain": "Data Protection",
      "capability_id": "public_data_exposure_prevention",
      "capability_name": "Public Data Exposure Prevention",
      "mapping_confidence": "high"
    },
    "maturity_context": [
      {
        "domain": "Data Protection",
        "capability_id": "public_data_exposure_prevention",
        "capability_name": "Public Data Exposure Prevention",
        "summary": "Protect data against unintended public exposure.",
        "recommended_practices": [
          "Restrict public access",
          "Continuously validate exposure controls"
        ],
        "score": 0.92
      }
    ]
  },
  "meta": {
    "index_version": "rag-v1-2026-03-15",
    "confidence": "high",
    "review_recommended": false
  },
  "errors": []
}
```

### Notes for Consumers
This endpoint is the default integration choice for the Analysis Module because it reduces orchestration complexity.

## 15.8 Health and Operational Endpoints

- `GET /health` — basic liveness
- `GET /ready` — readiness including index availability
- `GET /v1/index/info` — returns current index manifest and counts
- `POST /v1/index/rebuild` — optional admin-only trigger for controlled rebuild in non-production or internal admin mode

---

# 16. Error Handling

## 16.1 Error Categories

Supported categories:
- `validation_error`
- `not_found`
- `index_unavailable`
- `timeout`
- `internal_error`
- `unsupported_request`

## 16.2 Error Response Example

```json
{
  "request_id": "uuid",
  "status": "error",
  "data": {},
  "meta": {
    "index_version": "rag-v1-2026-03-15",
    "confidence": "low",
    "review_recommended": true
  },
  "errors": [
    {
      "code": "check_id_not_found",
      "message": "The requested check_id was not found in the current index."
    }
  ]
}
```

## 16.3 Error Design Guidance

An error should describe what failed in the retrieval contract, not merely that “something went wrong.”

Examples:
- good: `check_id_not_found`
- good: `index_unavailable`
- weak: `lookup_failed`

Clear errors make integration, retry logic, and review workflows much easier.

---

# 17. Shared State Contract

## 17.1 Purpose

RAG does not mutate agent state directly. However, agent modules may persist selected RAG output into shared state memory.

## 17.2 Recommended State Payload

```json
{
  "retrieved_context": {
    "request_id": "uuid",
    "index_version": "rag-v1-2026-03-15",
    "query_type": "context_build",
    "confidence": "high",
    "review_recommended": false,
    "check_id": "s3_account_level_public_access_blocks",
    "domain": "Data Protection",
    "capability_id": "public_data_exposure_prevention",
    "context_summary": {
      "check_title": "Ensure S3 account-level public access blocks are enabled",
      "maturity_capability": "Public Data Exposure Prevention"
    }
  }
}
```

## 17.3 State Storage Rules

Store only compact, decision-relevant context:
- `request_id`
- `confidence`
- selected `check_id`
- selected `domain` / `capability`
- short summaries
- source / index version

Do not store:
- full raw top-k retrieval lists unless specifically needed
- internal retrieval traces in shared memory

## 17.4 Why Shared State Must Stay Compact

Shared state should support orchestration, not duplicate the full retrieval system. Large raw retrieval traces are harder to maintain, harder to reason about, and unnecessary for most workflows.

---

# 18. Security and Access Control

## 18.1 Service Exposure

RAG v1 is internal-only and must not be publicly exposed.

## 18.2 Authentication

Recommended for v1:
- internal network access restriction
- optional shared service token or internal gateway auth

## 18.3 Sensitive Data Handling

The service should avoid indexing or logging:
- raw customer secrets
- credentials
- cloud account secrets
- unrelated environment-sensitive information

## 18.4 Logging Rules

Allowed:
- `request_id`
- endpoint
- query type
- filters
- result counts
- latency
- confidence
- index version

Avoid logging:
- raw sensitive finding payloads unless sanitized
- secrets or full credentials
- arbitrary unredacted environment metadata

## 18.5 Security Rationale

Even though RAG is not intended to store secrets, the surrounding assessment platform may process sensitive context. Therefore the RAG service should assume that some request payloads may contain environment information that should not be logged in full.

---

# 19. Observability

## 19.1 Required Logs

Each request should log:
- timestamp
- `request_id`
- endpoint
- `query_type`
- filters applied
- latency
- `result_count`
- confidence
- `review_recommended`
- `index_version`

## 19.2 Required Metrics

Minimum metrics:
- `request_count` by endpoint
- `error_count` by endpoint
- p50 / p95 latency by endpoint
- `no_result_count`
- `low_confidence_count`
- `mapping_missing_count`
- `index_version` currently loaded

## 19.3 Debug Mode

Debug mode may include:
- normalized query
- selected query type
- matched filters
- lexical top candidates
- vector top candidates
- merge notes

Debug mode must be disabled or protected in production-facing contexts unless explicitly enabled for internal debugging.

## 19.4 Why Observability Matters for RAG

RAG problems are often invisible if the system only returns a “reasonable-looking” result. Good observability makes it easier to detect:
- wrong-service retrieval
- overuse of low-confidence results
- stale mappings
- retrieval drift after corpus changes

---

# 20. Non-Functional Requirements

## 20.1 Reliability

The service should:
- respond consistently
- handle empty results gracefully
- return explicit failure states
- degrade safely if one retrieval backend fails

## 20.2 Performance Targets for v1

Suggested targets:
- p50 < 500 ms for simple lookups
- p95 < 1500 ms for hybrid retrieval
- context build within acceptable internal orchestration latency budget

These are practical targets, not hard SLAs for the first implementation.

## 20.3 Maintainability

Implementation must prioritize:
- simple code paths
- explicit schemas
- deterministic behavior
- easy offline rebuild
- reviewable mapping files

## 20.4 Scalability

RAG v1 is expected to support low-to-moderate internal traffic only.  
Massive scale is not a design goal for this version.

## 20.5 Testability

The service should be easy to test with:
- deterministic benchmark queries
- snapshot-based corpus inputs
- schema validation tests
- route-level API tests
- retrieval regression tests across index versions

---

# 21. Evaluation Plan

## 21.1 Purpose

Evaluation ensures the RAG service is good enough before being integrated into production agent flows.

## 21.2 Benchmark Types

### Benchmark A: Query -> Check Retrieval
Examples:
- natural language queries
- exact technical phrases
- bilingual queries
- exact `check_id` lookup

### Benchmark B: Check -> Mapping Resolution
Examples:
- verify correct domain/capability mapping for known reviewed checks

### Benchmark C: Finding -> Context Build
Examples:
- verify packaged context includes correct check, mapping, and maturity information

## 21.3 Metrics

Recommended metrics:
- top-1 accuracy for exact check lookup
- top-3 hit rate for natural language check search
- mapping accuracy
- no-result rate
- low-confidence rate
- wrong-service retrieval rate
- latency

## 21.4 Acceptance Criteria for v1

Suggested minimum acceptance criteria before wider integration:
- exact `check_id` lookup accuracy: 100% on benchmark set
- top-3 hit rate for check search: **>= 90%** on curated benchmark set
- mapping accuracy: **>= 95%** on reviewed mappings benchmark
- wrong-service rate: low and explicitly monitored
- no-result responses: explicit and explainable
- all APIs return schema-compliant responses

## 21.5 Evaluation Philosophy

The purpose of evaluation is not to prove perfection. It is to prove that the service is safe and useful enough to integrate without becoming a hidden source of analysis errors.

---

# 22. Implementation Guidance

## 22.1 Recommended Tech Stack for v1

- language: Python
- API framework: FastAPI
- schema validation: Pydantic
- lexical retrieval: BM25-based simple index
- vector retrieval: ChromaDB
- embeddings: `intfloat/multilingual-e5-base`
- storage: local filesystem + structured JSON
- packaging / deployment: simple containerized service

## 22.2 Suggested Internal Package Layout

```text
rag_service/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   ├── retrieve.py
│   │   │   ├── resolve.py
│   │   │   ├── build.py
│   │   │   └── health.py
│   ├── core/
│   │   ├── config.py
│   │   ├── logging.py
│   │   ├── models.py
│   │   └── errors.py
│   ├── ingestion/
│   │   ├── loaders.py
│   │   ├── normalizers.py
│   │   ├── enrichers.py
│   │   └── transformers.py
│   ├── indexing/
│   │   ├── build_index.py
│   │   ├── lexical_index.py
│   │   ├── vector_index.py
│   │   └── manifest.py
│   ├── retrieval/
│   │   ├── router.py
│   │   ├── lexical.py
│   │   ├── vector.py
│   │   ├── merger.py
│   │   ├── verifier.py
│   │   └── context_builder.py
│   └── services/
│       ├── maturity_service.py
│       ├── check_service.py
│       ├── mapping_service.py
│       └── context_service.py
├── data/
│   ├── raw/
│   ├── normalized/
│   ├── indexes/
│   └── benchmarks/
└── scripts/
    ├── build_all.py
    └── run_benchmarks.py
```

## 22.3 Suggested Service Responsibilities by Module

- `routes/`: HTTP contract only
- `services/`: use-case level orchestration
- `retrieval/`: router, retrieval engines, merging, verification
- `ingestion/`: transform raw source snapshots into normalized records
- `indexing/`: build and persist lexical/vector indexes
- `core/`: configuration, models, errors, logging setup

This separation helps keep the codebase understandable for new developers.

## 22.4 Suggested Development Order

A practical implementation order is:
1. define schemas and models
2. implement normalization pipeline
3. build exact lookup and lexical retrieval first
4. add vector retrieval
5. add merge + verification
6. add context build endpoint
7. add benchmark tests and regression checks

This order reduces risk because the system becomes useful before the full hybrid pipeline is complete.

---

# 23. Rollout Plan

## 23.1 Phase 1
- define schemas
- prepare normalized corpus
- implement offline build pipeline
- implement lexical + vector retrieval
- implement APIs
- run benchmark
- review with analysis / planning owners

## 23.2 Phase 2
- integrate with selected agent modules
- capture retrieval logs
- refine synonyms and mappings
- tune confidence and fallback

## 23.3 Phase 3
- optional reranking improvements
- broader integration with report or risk evaluation flows
- admin tooling for mapping review

## 23.4 Rollout Success Criteria

A phase should be considered successful when:
- the integration target can consume the API without custom workarounds
- benchmark results remain acceptable
- retrieval traces are understandable during debugging
- report-writing consumers can explain where their supporting context came from

---

# 24. Resolved Review Decisions

The following items are resolved for implementation kickoff:

1. **AWS maturity document snapshot/source format**  
   Cleaned Markdown files plus a normalized JSON extraction per capability will be used as the canonical ingestion source.

2. **Prowler check metadata source format**  
   Internal JSON snapshot generated from the reviewed Prowler metadata export will be used as the canonical ingestion source.

3. **Manual mapping ownership and review**  
   Manual mappings are owned by the Assessment Platform team and reviewed jointly by the security/domain reviewer plus platform maintainer before a mapping version is promoted.

4. **Top-3 hit rate acceptance threshold**  
   Initial acceptance threshold is set to **>= 90%** on the curated benchmark set.

5. **Reranking in first implementation**  
   Reranking support will exist in the interface, but active reranking is postponed by default for the first implementation.

6. **Preferred vector backend**  
   **ChromaDB** is the preferred backend for v1 because it is simple to operate and easy to inspect locally during development.

7. **Bilingual synonym dictionary maintenance**  
   Yes. A manually reviewed bilingual glossary will be maintained in v1 for the most common English/Vietnamese security phrases.

8. **First official integration target**  
   The first official integration target is the **Planning Module** for intent-to-check retrieval and the **Analysis Module** for context build consumption.

---

# 25. Final Architecture Decisions for v1

The following decisions are officially proposed for RAG v1:
- RAG is a standalone internal service
- RAG is retrieval-first, not answer-generation-first
- official knowledge sources are AWS Security Maturity Model and Prowler check metadata
- manual mapping is the authoritative source for check-to-capability mapping
- hybrid retrieval is used
- routing is primarily rule-based
- verification is lightweight and deterministic
- confidence is qualitative: `high` / `medium` / `low`
- low-confidence results explicitly recommend review
- RAG returns structured context, not final maturity decisions
- analysis and report generation remain outside the RAG service
- implementation favors simplicity, reviewability, and correctness over sophistication

## 25.1 Developer Interpretation of These Decisions

When there is ambiguity during implementation, prefer the option that is:
- easier to inspect
- easier to validate with tests
- easier to explain to reviewers
- less likely to hide retrieval mistakes

That preference is intentional and should guide trade-offs in v1.

---

# 26. Reporting Support Guidance

## 26.1 Purpose

This section exists to make the spec more useful for later reporting work. The RAG service does not generate final report text, but it should return enough structured context that report generation becomes straightforward and traceable.

## 26.2 Report-Relevant Fields

The following fields are especially useful for later report generation:
- `check_id`
- `title`
- `service`
- `severity`
- `description`
- `risk`
- `remediation`
- `domain`
- `capability_id`
- `capability_name`
- `summary`
- `recommended_practices`
- `mapping_reason`
- `mapping_confidence`
- `review_status`
- `index_version`
- `source_name`

## 26.3 Example Report Mapping

A later report generator may use RAG output like this:
- **Finding Title** <- `check_context.title`
- **Affected Service** <- `check_context.service`
- **Risk Summary** <- `check_context.risk`
- **Mapped Capability** <- `mapping_context.capability_name`
- **Why It Matters** <- `mapping_context.mapping_reason` + `maturity_context.summary`
- **Expected Practice** <- `maturity_context.recommended_practices`
- **Remediation Direction** <- `check_context.remediation`
- **Review Needed** <- `meta.review_recommended`

## 26.4 Important Reporting Rule

Report modules should distinguish between:
- technical fact from the check metadata
- maturity interpretation from the mapping layer
- final assessment judgment from the Analysis Module

These should not be collapsed into one undifferentiated sentence too early.

---

# 27. Sequence Flows

## 27.1 Sequence Flow A: Planning Query to Check Retrieval

1. Planning Module receives a natural-language user intent.
2. Planning Module calls `POST /v1/retrieve/checks`.
3. RAG normalizes the query and infers service/check intent.
4. RAG runs exact/lexical/vector retrieval as needed.
5. RAG returns ranked check candidates with confidence.
6. Planning Module selects target checks or asks for review if confidence is low.

## 27.2 Sequence Flow B: Finding to Analysis Context

1. Scanning Module produces a finding with `check_id` and metadata.
2. Analysis Module calls `POST /v1/build/context`.
3. RAG retrieves check context, mapping context, and maturity context.
4. RAG verifies consistency and returns structured package.
5. Analysis Module reasons over the package.
6. Report Module later consumes the resulting analysis output.

## 27.3 Sequence Flow C: Missing Mapping Case

1. Analysis Module sends a context build request.
2. RAG finds the check successfully.
3. No reviewed mapping exists.
4. RAG returns technical check context, empty or partial mapping context, `review_recommended = true`, and explicit issue `mapping_missing`.
5. Analysis Module avoids overstating capability alignment.

---

# 28. Appendix A - Sample Benchmark Entry

```json
[
  {
    "type": "check_search",
    "query": "kiểm tra public access block của S3",
    "expected_check_ids": [
      "s3_account_level_public_access_blocks",
      "s3_access_point_public_access_block"
    ],
    "provider": "aws",
    "service": "s3"
  },
  {
    "type": "mapping_resolution",
    "check_id": "s3_account_level_public_access_blocks",
    "expected_domain": "Data Protection",
    "expected_capability_id": "public_data_exposure_prevention"
  },
  {
    "type": "context_build",
    "finding": {
      "check_id": "s3_account_level_public_access_blocks",
      "service": "s3",
      "status": "FAIL"
    },
    "expected": {
      "check_present": true,
      "mapping_present": true,
      "maturity_present": true
    }
  }
]
```

---

# 29. Appendix B - Recommended Query Normalization Rules

## Normalize Technical Terms
- trim whitespace
- lowercase support text
- preserve IDs
- collapse duplicate spaces
- normalize hyphen / underscore variants where appropriate

## Bilingual Support
Map frequent Vietnamese security phrases to English retrieval terms:
- `mã hóa` -> `encryption`
- `truy cập công khai` -> `public access`
- `ghi log` -> `logging`
- `xoay vòng khóa` -> `key rotation`
- `quyền quá mức` -> `overly permissive access`

## Exact Lookup Detection
If query matches likely `check_id` pattern:
- prefer exact ID resolution path first

## Suggested Additional Rules
- preserve service tokens such as `s3`, `iam`, `ec2`
- do not over-normalize identifiers in a way that breaks exact lookup
- map common Vietnamese intent phrases like `kiểm tra`, `cấu hình`, `bật`, `tắt` into retrieval-support tokens only when useful

---

# 30. Appendix C - Minimum Review Checklist

Before implementation starts, reviewers should confirm:
- scope is acceptable for v1
- source-of-truth definitions are correct
- document schemas are acceptable
- API routes and envelopes are acceptable
- confidence and fallback policies are acceptable
- benchmark approach is acceptable
- implementation stack is acceptable
- first integration target is identified
- report support fields are sufficient for downstream use
- ownership of corpus snapshots and mappings is clear

---

# 31. Implementation Notes Added in v1.2

The following concrete choices are added in this revision to remove ambiguity before implementation:
- canonical embedding model for v1 baseline: `intfloat/multilingual-e5-base`
- canonical vector backend for v1 baseline: `ChromaDB`
- canonical benchmark target for natural-language check retrieval top-3 hit rate: `>= 90%`
- canonical first integration targets: `Planning Module` and `Analysis Module`
- canonical bilingual strategy: manually maintained reviewed glossary
- canonical report support principle: RAG returns structured evidence, not final report prose

## 31.1 Summary of What Changed in This Expanded Revision

Compared with the previous draft, this expanded revision adds:
- more explanatory text for implementers
- clearer interpretation of schemas and metadata
- more guidance for report-friendly outputs
- clearer sequence flows for integration
- stronger notes on validation, reproducibility, and developer-facing behavior

These additions are intended to reduce ambiguity during implementation and to make the document more usable as a long-term design reference.
