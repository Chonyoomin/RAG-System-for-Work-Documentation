from app.models.document import Document  # noqa: F401  -- register on Base.metadata
from app.models.system_info import SystemInfo  # noqa: F401  -- register on Base.metadata

__all__ = ["Document", "SystemInfo"]
