from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import time
from .config import settings


def _get_db_url() -> str:
    """Prefer os.environ DATABASE_URL (Heroku), else settings (local .env)."""
    url = os.environ.get("DATABASE_URL")
    if not (url and url.strip()):
        # On Heroku (PORT set), never fall back to localhost
        if os.environ.get("PORT"):
            raise RuntimeError(
                "DATABASE_URL not set on Heroku. Check addon attachment and config vars."
            )
        url = settings.get_database_url()
    url = (url or "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL or DB settings must be set")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[10:]
    # Ensure SSL for Heroku Postgres (remote URLs)
    if "localhost" not in url and "sslmode" not in url and "@" in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


def _creator():
    """Creator that connects with explicit URL; clears libpq env to avoid override."""
    libpq_vars = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSERVICE")
    saved = {k: os.environ.pop(k, None) for k in libpq_vars}
    try:
        return psycopg2.connect(SQLALCHEMY_DATABASE_URL)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


SQLALCHEMY_DATABASE_URL = _get_db_url()
# Use creator to bypass SQLAlchemy's URL handling; psycopg2.connect(url) with cleared PG* env
engine = create_engine("postgresql://", creator=_creator)

SessionLocal = sessionmaker(autocommit=False,autoflush=False,bind=engine)

Base = declarative_base()
#Sql alchemy db set up
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()