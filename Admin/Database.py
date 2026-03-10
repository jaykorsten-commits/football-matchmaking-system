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


SQLALCHEMY_DATABASE_URL = _get_db_url()
engine = create_engine(SQLALCHEMY_DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False,autoflush=False,bind=engine)

Base = declarative_base()
#Sql alchemy db set up
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()