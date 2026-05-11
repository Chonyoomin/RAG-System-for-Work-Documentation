from pathlib import Path

from alembic import command
from alembic.config import Config


def init_db() -> None:
    backend_dir = Path(__file__).resolve().parents[2]
    alembic_ini = backend_dir / "alembic.ini"

    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(backend_dir / "migrations"))

    command.upgrade(config, "head")


if __name__ == "__main__":
    init_db()
