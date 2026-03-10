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


# Clear libpq env vars so they can't override DATABASE_URL when pool connects (lazy)
libpq = ("PGHOST", "PGHOSTADDR", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSERVICE")
for k in libpq:
    os.environ.pop(k, None)

engine = create_engine(_get_db_url(), pool_pre_ping=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
