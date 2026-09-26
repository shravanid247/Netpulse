import os
from pathlib import Path
from collections.abc import Generator
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Load .env file from project root or backend directory
root_dir = Path(__file__).resolve().parents[3]
dotenv_path = root_dir / ".env"
if dotenv_path.is_file():
    load_dotenv(dotenv_path)
else:
    load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://netpulse_user@localhost:5432/netpulse",
)

# Normalize postgresql:// to postgresql+psycopg2:// for psycopg2-binary
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

engine_kwargs = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables() -> None:
    from app.db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

def check_db_connection() -> tuple[bool, str]:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "Database connection successful"
    except Exception as exc:
        # Avoid exposing raw connection strings/passwords in error output
        error_msg = str(exc).split("\n")[0]
        return False, f"Connection failed: {error_msg}"

