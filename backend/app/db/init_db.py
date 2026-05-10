from sqlalchemy import text

from app.db.base import Base
from app.db.session import engine


def init_db() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    init_db()
