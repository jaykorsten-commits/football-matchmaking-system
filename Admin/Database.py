from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import time
from .config import settings

def _get_db_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[10:]
        return url
    return settings.get_database_url()

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