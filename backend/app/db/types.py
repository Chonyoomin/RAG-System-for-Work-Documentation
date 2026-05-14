import json

from pgvector.sqlalchemy import Vector
from sqlalchemy.types import Text, TypeDecorator


class EmbeddingVector(TypeDecorator):
    """pgvector ``Vector(dim)`` on PostgreSQL, JSON-encoded list elsewhere.

    Lets the same model run against Postgres in production and SQLite in tests
    without forking the schema. SQLite path is for shape/metadata tests only;
    real similarity ops require Postgres + pgvector.
    """
    impl = Text
    cache_ok = True

    def __init__(self, dim: int):
        super().__init__()
        self.dim = dim

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(Vector(self.dim))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return json.dumps(list(value))

    def process_result_value(self, value, dialect):
        if value is None or dialect.name == "postgresql":
            return value
        return json.loads(value)
