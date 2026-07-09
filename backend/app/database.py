from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings


settings = get_settings()

if settings.database_url.startswith("sqlite:///"):
    db_path = Path(settings.database_url.replace("sqlite:///", "", 1))
    db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def init_db() -> None:
    from app import models

    Base.metadata.create_all(bind=engine)
    ensure_columns()


def ensure_columns() -> None:
    inspector = inspect(engine)
    if "creative_points" not in inspector.get_table_names():
        return

    columns = {item["name"] for item in inspector.get_columns("creative_points")}
    with engine.begin() as connection:
        if "source_round" not in columns:
            connection.execute(text("ALTER TABLE creative_points ADD COLUMN source_round INTEGER NOT NULL DEFAULT 1"))
        if "discovery_reason" not in columns:
            connection.execute(text("ALTER TABLE creative_points ADD COLUMN discovery_reason TEXT NOT NULL DEFAULT ''"))
        if "application_scenarios_json" not in columns:
            connection.execute(text("ALTER TABLE creative_points ADD COLUMN application_scenarios_json TEXT NOT NULL DEFAULT '[]'"))
        if "plain_explanation" not in columns:
            connection.execute(text("ALTER TABLE creative_points ADD COLUMN plain_explanation TEXT NOT NULL DEFAULT ''"))
        if "image_status" not in columns:
            connection.execute(text("ALTER TABLE creative_points ADD COLUMN image_status VARCHAR(30) NOT NULL DEFAULT 'idle'"))
        if "image_url" not in columns:
            connection.execute(text("ALTER TABLE creative_points ADD COLUMN image_url TEXT NOT NULL DEFAULT ''"))
        if "image_prompt" not in columns:
            connection.execute(text("ALTER TABLE creative_points ADD COLUMN image_prompt TEXT NOT NULL DEFAULT ''"))
        if "image_error" not in columns:
            connection.execute(text("ALTER TABLE creative_points ADD COLUMN image_error TEXT NOT NULL DEFAULT ''"))
        if "image_created_at" not in columns:
            connection.execute(text("ALTER TABLE creative_points ADD COLUMN image_created_at TIMESTAMP NULL"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
