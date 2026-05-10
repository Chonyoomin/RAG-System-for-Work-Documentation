# Architecture

## Why LlamaIndex

LlamaIndex provides ingestion, parsing, indexing, and citation-aware retrieval primitives that are well-suited for source-grounded RAG. Its node and metadata model preserves document / page / chunk provenance natively, which is the central requirement of this project. Using it avoids hand-rolling chunking, indexing, and citation plumbing.

## Why LangChain

LangChain is used for embeddings integration, vector store / retriever wiring, and optional runtime orchestration. It offers consistent adapters for embedding models and pgvector, and slot-in retrievers that compose cleanly with LlamaIndex outputs. We use it for plumbing only — not for answer-quality logic.

## Why PostgreSQL + pgvector

A single dependable store for both relational metadata (documents, pages, chunks, ingestion state) and vector embeddings. This keeps the stack small, portable, and cheap to run, and avoids introducing a separate managed vector database for a prototype.

## Why OCR is Included Early

Real work-style documents are often scanned PDFs or image-heavy exports. Without OCR, large portions of the corpus would be silently invisible to retrieval, breaking source grounding. Tesseract runs locally with no recurring cost and is sufficient for prototype quality.

## Custom vs Framework-Managed

**Framework-managed (LlamaIndex / LangChain):**
- Document loading and parsing
- Chunking and node construction
- Embedding generation and vector store I/O
- Base retrieval and citation extraction

**Kept explicit / custom:**
- Source-grounding policy (no source, no answer)
- Citation integrity checks (cited chunks must be the chunks actually retrieved)
- Exact-quote extraction and verification against the source text
- No-answer decision logic when evidence is insufficient
- Provenance schema (document id, page number, chunk index)

Frameworks replace plumbing, not quality controls.

## Intended Pipeline

1. **Upload** — user submits a synthetic document via the FastAPI backend.
2. **Parse** — extract text using PyMuPDF (PDF), python-docx (DOCX), or Pillow + Tesseract (images and scanned pages).
3. **Chunk** — deterministic chunking via LlamaIndex, attaching `{document_id, page, chunk_index}` metadata to every node.
4. **Embed** — generate embeddings with the configured local embedding model.
5. **Persist** — store chunks, metadata, and vectors in PostgreSQL + pgvector.
6. **Retrieve** — on query, run citation-aware retrieval to fetch top-k chunks with provenance.
7. **Answer** — generate a response strictly grounded in retrieved chunks, including citations and verbatim supporting quotes. If retrieval evidence is insufficient, return a no-answer result instead of generating an unsupported answer.
