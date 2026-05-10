# AGENTS.md

Repository instructions for Codex and other repo-aware coding agents working on this project.

## Project Objective

Build a source-grounded documentation retrieval system that ingests work-style documents and returns answers with citations and exact supporting quotes. The system must return a clear no-answer result when retrieval evidence is insufficient.

## Architecture Direction

- **LlamaIndex** — ingestion, parsing, indexing, citation-aware retrieval
- **LangChain** — embeddings integration, vector store / retriever wiring, optional runtime orchestration
- **PostgreSQL + pgvector** — persistence and vector storage
- **FastAPI** — backend API
- **React + TypeScript** — frontend
- **Tesseract** — local OCR for image-heavy or scanned documents

Prefer framework-native solutions over custom RAG plumbing. Frameworks replace plumbing, not quality controls.

## Core Design Rules

- Source-backed answers only. No source, no answer.
- Preserve document / page / chunk provenance through every stage.
- Support exact supporting quotes from source documents.
- Use OCR for image-heavy or scanned input.
- Deterministic preprocessing where possible.
- Avoid LLM-heavy logic outside the parts that truly need it.
- Keep recurring costs low.

## Public GitHub Safety Rules

This repository is public. Never commit:

- Proprietary, customer, or internal documents
- Internal screenshots
- Real customer / employee / internal identifiers
- Secrets, API keys, tokens, real config values
- Logs, OCR output, processed outputs, vector artifacts, or caches derived from private documents
- User uploads containing real source files

Only synthetic, fictional, or fully redacted sample data is permitted. Use placeholder configuration values and strong ignore rules.

## Phase-Based Development Outline

- **Phase 0 — Foundation (current).** Repository scaffolding, documentation, safety guardrails, placeholder config. No application logic.
- **Phase 1 — Ingestion.** Document upload, parsing, OCR fallback, deterministic chunking, provenance preservation.
- **Phase 2 — Indexing.** Embedding generation and pgvector persistence via LlamaIndex / LangChain.
- **Phase 3 — Retrieval.** Citation-aware retrieval returning chunks with document / page / chunk references.
- **Phase 4 — Answering.** Source-grounded answer generation with citations, exact supporting quotes, and a no-answer path when evidence is insufficient.
- **Phase 5 — MVP UI.** Minimal React + TypeScript frontend for upload, query, and citation display.
- **Later (optional).** Re-ranking, evaluation harness, hybrid search, auth, multi-tenant scoping, deployment hardening.

## Review Priorities

When reviewing changes, prioritize:

1. **Source grounding** — answers must cite real retrieved chunks; do not allow ungrounded generation paths.
2. **Citation integrity** — citations must point to the chunk actually used; quotes must be verbatim from the source.
3. **Provenance** — document / page / chunk references preserved end-to-end.
4. **Portfolio safety** — no private data, secrets, or derived artifacts may slip into the repo.
5. **Avoid unnecessary custom infrastructure** — prefer LlamaIndex / LangChain primitives over hand-rolled RAG plumbing.
6. **Scope discipline** — no premature abstraction, no speculative services, no overengineering.
