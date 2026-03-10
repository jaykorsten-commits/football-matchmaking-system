from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from .config import settings


def _get_db_url() -> str:
    """Use DATABASE_URL from env; never fall back to localhost on Heroku (PORT set)."""
    url = (os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        if os.environ.get("PORT"):
            raise RuntimeError(
                "DATABASE_URL is empty on Heroku. Web dyno may not receive addon vars. PORT="
                + repr(os.environ.get("PORT"))
            )
        url = settings.get_database_url()
    if not url:
        raise RuntimeError("DATABASE_URL or DB settings must be set")
    if url.startswith("postgres://"):
        url = "postgresql://" + url[10:]
    # Heroku gives postgres:///user:pass@host/db (3 slashes) - fix so netloc is parsed
    if url.startswith("postgresql:///") and "@" in url:
        url = "postgresql://" + url[13:]  # remove one slash: /// -> //
    if "localhost" not in url and "sslmode" not in url and "@" in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


_url = _get_db_url()
engine = create_engine(_url, pool_pre_ping=True)

print(f"[BOOT] raw _url prefix: {repr(_url[:120])}", flush=True)
print(f"[BOOT] engine url: {engine.url.render_as_string(hide_password=True)}", flush=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    print(f"[REQ] engine url: {engine.url.render_as_string(hide_password=True)}", flush=True)
    print(f"[REQ] engine id: {id(engine)}", flush=True)
    print(f"[REQ] SessionLocal id: {id(SessionLocal)}", flush=True)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
