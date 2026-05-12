# Documentation RAG

A portfolio prototype for source-grounded retrieval over work-style documents. The system ingests documents, indexes them with provenance, and answers questions with citations and exact supporting quotes. When evidence is insufficient, it returns a clear no-answer result.

## Purpose

Demonstrate product thinking and system design for a small, honest RAG system that prioritizes source traceability and citation integrity over flashy generation.

## MVP Scope

- Upload synthetic documents (PDF, DOCX, images)
- Extract text with OCR fallback for image-heavy or scanned files
- Index with LlamaIndex and store vectors in PostgreSQL + pgvector
- Retrieve relevant chunks with document/page/chunk provenance
- Generate answers with citations and exact supporting quotes
- Return a no-answer result when retrieval evidence is insufficient

## High-Level Architecture

- **Ingestion / indexing / citation-aware retrieval:** LlamaIndex
- **Embeddings + retriever wiring + optional runtime orchestration:** LangChain
- **Persistence + vector store:** PostgreSQL + pgvector
- **Backend API:** FastAPI
- **Frontend:** React + TypeScript
- **OCR:** Tesseract (local)

## Key Design Rules

- Source-backed answers only — no source means no answer
- Preserve document / page / chunk provenance end-to-end
- Support exact supporting quotes from source documents
- Deterministic preprocessing where possible
- Frameworks replace plumbing, not quality controls
- Keep recurring costs low

## Sample Data

This repository contains only **synthetic, fictional, or fully redacted** sample data. No proprietary documents, internal screenshots, customer identifiers, secrets, or derived artifacts from private sources are committed. See [docs/github-safety.md](docs/github-safety.md).

## Status

Current state: foundation plus early backend upload/bootstrap work. The full `Phase 1` target in [AGENTS.md](AGENTS.md) also includes parsing, OCR fallback, deterministic chunking, and provenance preservation, which are not implemented yet.
