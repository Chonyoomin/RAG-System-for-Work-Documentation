# CLAUDE.md

Instructions for Claude Code working in this repository.

## Project Objective

A source-grounded documentation retrieval prototype. The system ingests work-style documents and answers questions with citations and exact supporting quotes. When evidence is insufficient, it returns a clear no-answer result.

## Architecture Direction

- **LlamaIndex** — ingestion, parsing, indexing, citation-aware retrieval
- **LangChain** — embeddings, vector store / retriever wiring, optional orchestration
- **PostgreSQL + pgvector** — persistence and vector storage
- **FastAPI** — backend
- **React + TypeScript** — frontend
- **Tesseract** — local OCR

## Build Philosophy

- This is a prototype. Avoid overengineering.
- Prefer framework-native solutions in LlamaIndex and LangChain over custom RAG plumbing.
- Frameworks replace plumbing, not quality controls — keep source-grounding and citation logic explicit and verifiable.
- Deterministic preprocessing where possible. Reserve LLM calls for steps that truly need them.
- Keep recurring costs low.
- No speculative abstractions, no half-finished implementations, no extra services beyond what each phase requires.

## Public Repo Safety Constraints

This repository is public.

- Never commit proprietary documents, internal screenshots, real identifiers, secrets, tokens, or real config values.
- Never commit logs, OCR output, processed outputs, vector artifacts, or caches derived from private documents.
- Only synthetic, fictional, or fully redacted sample data is allowed.
- Use placeholder values in `.env.example`. Real `.env` files are git-ignored.
- See [docs/github-safety.md](docs/github-safety.md) before adding any data, fixture, or output file.

## Coding Priorities

1. Source grounding — every answer must trace back to a retrieved chunk.
2. Citation integrity — citations must point to the chunk actually used; supporting quotes must be verbatim.
3. Provenance — preserve document / page / chunk references through every stage.
4. Determinism — keep parsing, chunking, and ranking reproducible where possible.
5. Simplicity — minimal, readable code; no premature abstraction.
6. Safety — never weaken portfolio-safety guardrails to make a task easier.

## Token Efficiency for Code Generation

- Output only the final code; no prose around it.
- No restatement of the task.
- Comments only where logic is non-obvious. No docstrings unless required for functionality. No block comments.

## Phase Awareness

Check [docs/project-scope.md](docs/project-scope.md) for the current phase before adding anything. Do not implement features from later phases unless explicitly asked.
