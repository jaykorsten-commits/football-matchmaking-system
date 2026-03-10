from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
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
    if "localhost" not in url and "sslmode" not in url and "@" in url:
        sep = "&" if "?" in url else "?"
        url = url + sep + "sslmode=require"
    return url


_url = _get_db_url()
_parsed = make_url(_url)  # SQLAlchemy parser handles postgresql:// correctly
_connect_args = {}
if _parsed.host and "localhost" not in (_parsed.host or ""):
    _connect_args["host"] = _parsed.host
    _connect_args["port"] = _parsed.port or 5432
    _connect_args["sslmode"] = "require"
engine = create_engine(_url, pool_pre_ping=True, connect_args=_connect_args)

print("[BOOT] simplified Database.py loaded", flush=True)
print(engine.url.render_as_string(hide_password=True), flush=True)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
