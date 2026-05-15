import codecs
import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_session
from app.models import Chunk, ChunkEmbedding, Document, Page
from app.services import chunking, extraction, indexing, ingestion, storage

router = APIRouter(prefix="/documents", tags=["documents"])

_READ_CHUNK = 64 * 1024
# Generous allowance for multipart envelope overhead so the early Content-Length
# check never false-rejects a file that's legitimately at or under the limit.
_EARLY_REJECT_SLACK = 1 * 1024 * 1024


def _to_dict(d: Document) -> dict:
    return {
        "id": d.id,
        "original_filename": d.original_filename,
        "stored_filename": d.stored_filename,
        "mime_type": d.mime_type,
        "size_bytes": d.size_bytes,
        "content_hash": d.content_hash,
        "status": d.status,
        "uploaded_at": d.uploaded_at.isoformat(),
    }


def _too_large(size: int, limit: int) -> HTTPException:
    return HTTPException(
        status_code=413,
        detail={"error": "file_too_large", "size_bytes": size, "limit_bytes": limit},
    )


def _invalid_content(reason: str) -> HTTPException:
    return HTTPException(
        status_code=415,
        detail={"error": "invalid_content", "reason": reason},
    )


@router.post("/upload", status_code=201)
async def upload(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename missing")

    extension = storage.extension_for(file.filename)
    if extension not in storage.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail={
                "error": "unsupported_file_type",
                "extension": extension or "<none>",
                "allowed": sorted(storage.ALLOWED_EXTENSIONS),
            },
        )

    limit = settings.max_upload_bytes

    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            declared_size = int(declared)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > limit + _EARLY_REJECT_SLACK:
            raise _too_large(declared_size, limit)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = settings.upload_dir / f".incoming-{uuid.uuid4().hex}"

    hasher = hashlib.sha256()
    total = 0
    text_decoder = (
        codecs.getincrementaldecoder("utf-8")() if extension in {".txt", ".md"} else None
    )
    first_chunk = True

    try:
        with tmp_path.open("wb") as tmp:
            while True:
                chunk = await file.read(_READ_CHUNK)
                if not chunk:
                    break
                if first_chunk:
                    first_chunk = False
                    if extension == ".pdf" and not chunk.startswith(storage.PDF_MAGIC):
                        raise _invalid_content("missing PDF signature (expected '%PDF-')")
                    if extension == ".docx" and not chunk.startswith(storage.ZIP_MAGIC):
                        raise _invalid_content("missing DOCX/ZIP signature")
                total += len(chunk)
                if total > limit:
                    raise _too_large(total, limit)
                if text_decoder is not None:
                    if b"\x00" in chunk:
                        raise _invalid_content("text contains NUL bytes")
                    try:
                        text_decoder.decode(chunk, final=False)
                    except UnicodeDecodeError:
                        raise _invalid_content("not valid UTF-8")
                hasher.update(chunk)
                tmp.write(chunk)

        if text_decoder is not None:
            try:
                text_decoder.decode(b"", final=True)
            except UnicodeDecodeError:
                raise _invalid_content("not valid UTF-8 (truncated sequence)")

        if total == 0:
            raise HTTPException(status_code=400, detail="empty file")

        if extension == ".docx":
            problem = storage.validate_docx_structure(tmp_path)
            if problem:
                raise _invalid_content(problem)

        content_hash = hasher.hexdigest()
        try:
            document = ingestion.persist_upload(
                session,
                original_filename=file.filename,
                tmp_path=tmp_path,
                extension=extension,
                content_hash=content_hash,
                size_bytes=total,
            )
        except ingestion.DuplicateDocument as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "duplicate",
                    "existing_id": exc.existing.id,
                    "content_hash": exc.existing.content_hash,
                },
            )
    finally:
        tmp_path.unlink(missing_ok=True)

    return _to_dict(document)


@router.get("/")
def list_documents(session: Session = Depends(get_session)):
    rows = session.query(Document).order_by(Document.id).all()
    return [_to_dict(d) for d in rows]


@router.get("/{document_id}")
def get_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return _to_dict(document)


@router.post("/{document_id}/extract")
def extract_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    try:
        result = extraction.extract_and_persist(session, document)
    except extraction.ExtractionError as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "extraction_failed", "reason": str(exc)},
        )
    return {
        "document_id": document.id,
        "status": document.status,
        "page_count": result.page_count,
        "sources": result.sources,
    }


@router.get("/{document_id}/pages")
def list_pages(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    pages = (
        session.query(Page)
        .filter_by(document_id=document_id)
        .order_by(Page.page_number)
        .all()
    )
    return [
        {"page_number": p.page_number, "source": p.source, "text": p.text}
        for p in pages
    ]


@router.post("/{document_id}/chunk")
def chunk_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    try:
        result = chunking.chunk_and_persist(session, document)
    except chunking.ChunkingError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "chunking_failed", "reason": str(exc)},
        )
    return {
        "document_id": document.id,
        "status": document.status,
        "chunk_count": result.chunk_count,
        "page_count": result.page_count,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
    }


@router.get("/{document_id}/chunks")
def list_chunks(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    chunks = (
        session.query(Chunk)
        .filter_by(document_id=document_id)
        .order_by(Chunk.page_number, Chunk.chunk_index)
        .all()
    )
    return [
        {
            "page_number": c.page_number,
            "chunk_index": c.chunk_index,
            "char_start": c.char_start,
            "char_end": c.char_end,
            "text": c.text,
        }
        for c in chunks
    ]


@router.post("/{document_id}/index")
def index_document(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    try:
        result = indexing.index_document(session, document)
    except indexing.IndexingError as exc:
        raise HTTPException(
            status_code=409,
            detail={"error": "indexing_failed", "reason": str(exc)},
        )
    return {
        "document_id": document.id,
        "status": document.status,
        "chunk_count": result.chunk_count,
        "indexed_count": result.indexed_count,
        "embedding_model": result.embedding_model,
        "embedding_dim": result.embedding_dim,
    }


@router.get("/{document_id}/index")
def index_coverage(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    cov = indexing.coverage(session, document)
    return {
        "document_id": document.id,
        "status": document.status,
        "chunk_count": cov.chunk_count,
        "indexed_count": cov.indexed_count,
        "is_fully_indexed": cov.is_fully_indexed,
        "embedding_models": cov.embedding_models,
    }


@router.get("/{document_id}/embeddings")
def list_embeddings(document_id: int, session: Session = Depends(get_session)):
    document = session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    rows = (
        session.query(ChunkEmbedding)
        .filter_by(document_id=document_id)
        .order_by(
            ChunkEmbedding.embedding_model,
            ChunkEmbedding.page_number,
            ChunkEmbedding.chunk_index,
        )
        .all()
    )
    return [
        {
            "chunk_id": r.chunk_id,
            "page_number": r.page_number,
            "chunk_index": r.chunk_index,
            "embedding_model": r.embedding_model,
            "embedding_dim": r.embedding_dim,
        }
        for r in rows
    ]
