# Project Scope

## MVP Target

A working end-to-end loop on synthetic documents:

1. Upload synthetic documents.
2. Extract text, with OCR fallback for image-heavy or scanned files.
3. Index with LlamaIndex.
4. Store vectors in PostgreSQL + pgvector.
5. Retrieve relevant chunks with document / page / chunk provenance.
6. Generate an answer with citations and exact supporting quotes.
7. Return a clear no-answer result when retrieved evidence is insufficient.

## In Scope

- Local document upload and parsing for PDF, DOCX, and image inputs
- Tesseract OCR for scanned or image-heavy pages
- Deterministic chunking with preserved provenance (doc id, page, chunk index)
- Embedding generation via a local model (default: `BAAI/bge-small-en-v1.5`)
- Vector storage and similarity search in pgvector
- Citation-aware retrieval via LlamaIndex
- Source-grounded answer generation with verbatim supporting quotes
- Explicit no-answer path when retrieval evidence is insufficient
- Minimal FastAPI backend and React + TypeScript frontend for the MVP loop

## Intentionally Deferred

- Authentication, multi-tenant scoping, role-based access
- Hybrid (BM25 + vector) search and re-rankers
- Evaluation harness and regression test corpus beyond a small synthetic set
- Background workers, queues, async ingestion pipelines
- Production deployment, observability, alerting
- Document versioning, edit tracking, diffing
- Streaming responses, conversational memory
- Cloud-hosted embedding or OCR services

## Success Criteria for the First Working Prototype

- A user can upload a synthetic document and receive a citation-backed answer that includes a verbatim supporting quote.
- Every answer either cites at least one retrieved chunk or returns a no-answer result.
- Citations resolve back to a real document, page, and chunk in the index.
- The repository remains portfolio-safe: no proprietary data, no secrets, no private artifacts.
- The codebase is small, readable, and uses LlamaIndex / LangChain primitives instead of bespoke RAG plumbing.

## Phase Plan

- **Phase 0 (current)** — Repository foundation, documentation, safety guardrails, scaffolding.
- **Phase 1** — Ingestion: parsing, OCR fallback, deterministic chunking with provenance.
- **Phase 2** — Indexing: embeddings + pgvector persistence.
- **Phase 3** — Retrieval: citation-aware retrieval over the index.
- **Phase 4** — Answering: source-grounded generation, exact quotes, no-answer path.
- **Phase 5** — MVP UI: upload, query, citation display.
- **Later (optional)** — Re-ranking, evaluation, hybrid search, auth, deployment hardening.
