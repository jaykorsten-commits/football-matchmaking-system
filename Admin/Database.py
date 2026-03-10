from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from .config import settings


def _get_db_url() -> str:
    """Use DATABASE_URL from env; never fall back to localhost on Heroku."""
    url = os.environ.get("DATABASE_URL")
    if not (url and url.strip()):
        if os.environ.get("PORT"):
            raise RuntimeError("DATABASE_URL missing on Heroku")
        url = settings.get_database_url()
    url = (url or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL or DB settings must be set")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[10:]
    if "localhost" not in url and "sslmode" not in url and "@" in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


def _create_engine():
    """Create engine; clear libpq env vars so they can't override DATABASE_URL."""
    libpq = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSERVICE")
    saved = {k: os.environ.pop(k, None) for k in libpq}
    try:
        return create_engine(_get_db_url(), pool_pre_ping=True)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


engine = _create_engine()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
