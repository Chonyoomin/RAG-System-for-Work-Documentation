from app.db.base import Base
from app.models import Document, SystemInfo


def test_system_info_registered_on_metadata():
    assert SystemInfo.__tablename__ == "system_info"
    assert "system_info" in Base.metadata.tables

    columns = {c.name for c in Base.metadata.tables["system_info"].columns}
    assert {"id", "key", "value", "updated_at"} <= columns


def test_document_registered_on_metadata():
    assert Document.__tablename__ == "documents"
    assert "documents" in Base.metadata.tables

    columns = {c.name for c in Base.metadata.tables["documents"].columns}
    assert {
        "id",
        "original_filename",
        "stored_filename",
        "mime_type",
        "size_bytes",
        "content_hash",
        "status",
        "uploaded_at",
    } <= columns
