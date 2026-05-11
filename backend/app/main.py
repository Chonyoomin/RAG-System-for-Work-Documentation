import logging

from fastapi import FastAPI

from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(health_router)
app.include_router(documents_router)
