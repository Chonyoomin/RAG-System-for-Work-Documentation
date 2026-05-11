from app.db.base import Base
from app.models import SystemInfo


def test_system_info_registered_on_metadata():
    assert SystemInfo.__tablename__ == "system_info"
    assert "system_info" in Base.metadata.tables

    columns = {c.name for c in Base.metadata.tables["system_info"].columns}
    assert {"id", "key", "value", "updated_at"} <= columns
