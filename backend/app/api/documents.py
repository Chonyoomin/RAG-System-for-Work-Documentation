from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import Document
from app.services import ingestion, storage

router = APIRouter(prefix="/documents", tags=["documents"])


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


@router.post("/upload", status_code=201)
async def upload(
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="filename missing")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty file")

    try:
        document = ingestion.ingest(session, file.filename, data)
    except ingestion.UnsupportedFileType as exc:
        raise HTTPException(
            status_code=415,
            detail={
                "error": "unsupported_file_type",
                "extension": exc.extension,
                "allowed": sorted(storage.ALLOWED_EXTENSIONS),
            },
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
