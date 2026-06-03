"""
Database layer (SQLAlchemy).

Two tables:
* ``users`` — credentials + API key for the product web app and API.
* ``scans`` — scan records with the full JSON result for history/results.

Defaults to SQLite for zero-config local runs; docker-compose points
``DATABASE_URL`` at PostgreSQL.
"""
from __future__ import annotations

import datetime as _dt
import json
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from . import config

# ``check_same_thread`` only matters for SQLite; harmless otherwise.
_connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=_connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    api_key = Column(String(64), unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    scans = relationship("Scan", back_populates="user", cascade="all, delete-orphan")


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True)
    scan_id = Column(String(36), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    filename = Column(String(512), nullable=False)
    media_type = Column(String(16), nullable=False)
    status = Column(String(16), default="processing")  # processing|done|error
    score = Column(Float, nullable=True)
    verdict = Column(String(32), nullable=True)
    result_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_dt.datetime.utcnow)

    user = relationship("User", back_populates="scans")

    def result(self) -> Optional[dict]:
        return json.loads(self.result_json) if self.result_json else None


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session():
    """FastAPI dependency that yields a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
