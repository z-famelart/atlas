"""Persistent LLM response cache — Feature 07.

Cache key = SHA-256(instructions + content + schema_version + provider_id).
Stored in SQLite alongside the facts database so it survives across runs.
Invalidation is implicit: prompt content change → different hash → cache miss.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from .types import StructuredPrompt


class _Base(DeclarativeBase):
    pass


class _CacheRow(_Base):
    __tablename__ = "llm_cache"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    response_json: Mapped[str] = mapped_column(Text)


def cache_key(prompt: StructuredPrompt, provider_id: str) -> str:
    raw = f"{prompt.instructions}\x00{prompt.content}\x00{prompt.schema_version}\x00{provider_id}"
    return hashlib.sha256(raw.encode()).hexdigest()


class LLMCache:
    def __init__(self, db_path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{db_path}", echo=False)
        _Base.metadata.create_all(self._engine)
        self._Session = Session(self._engine)

    def get(self, key: str) -> str | None:
        with Session(self._engine) as session:
            row = session.get(_CacheRow, key)
            return row.response_json if row else None

    def set(self, key: str, value: str) -> None:
        with Session(self._engine) as session:
            existing = session.get(_CacheRow, key)
            if existing:
                existing.response_json = value
            else:
                session.add(_CacheRow(key=key, response_json=value))
            session.commit()

    def close(self) -> None:
        self._engine.dispose()
