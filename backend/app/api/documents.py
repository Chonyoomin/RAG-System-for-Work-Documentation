import codecs
import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_session
from app.models import Document
from app.services import ingestion, storage

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
