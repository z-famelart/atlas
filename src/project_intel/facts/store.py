"""SQLAlchemy-backed FactStore."""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import cattrs
from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, create_engine, func, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .enums import EntityType
from .model import Entity, EntityRef, Evidence, Fact
from .refs import KIND_TO_REF_CLASS

SCHEMA_VERSION = "1.0"


class SchemaVersionError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# ORM models (internal — not part of the public API)
# ---------------------------------------------------------------------------


class _Base(DeclarativeBase):
    pass


class _SchemaMetaRow(_Base):
    __tablename__ = "schema_meta"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)


class _EvidenceRow(_Base):
    __tablename__ = "fact_evidence"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    fact_id: Mapped[str] = mapped_column(ForeignKey("facts.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    ref: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_analyzer: Mapped[str] = mapped_column(String, nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    fact: Mapped[_FactRow] = relationship(back_populates="evidence_rows")


class _FactRow(_Base):
    __tablename__ = "facts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    subject_type: Mapped[str] = mapped_column(String, nullable=False)
    subject_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    predicate: Mapped[str | None] = mapped_column(String, nullable=True)
    object_type: Mapped[str | None] = mapped_column(String, nullable=True)
    object_id: Mapped[str | None] = mapped_column(String, nullable=True)
    value: Mapped[Any | None] = mapped_column(JSON, nullable=True)
    provenance: Mapped[str] = mapped_column(String, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_analyzer: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)
    run_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    evidence_rows: Mapped[list[_EvidenceRow]] = relationship(
        cascade="all, delete-orphan", back_populates="fact"
    )


class _EntityRow(_Base):
    __tablename__ = "entities"

    type: Mapped[str] = mapped_column(String, primary_key=True)
    id: Mapped[str] = mapped_column(String, primary_key=True)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    repository_id: Mapped[str | None] = mapped_column(String, nullable=True)
    schema_version: Mapped[str] = mapped_column(String, nullable=False)


# ---------------------------------------------------------------------------
# Cattrs converter for EvidenceRef deserialization
# ---------------------------------------------------------------------------

_converter = cattrs.Converter()


def _structure_ref(kind: str, data: dict[str, Any]) -> Any:
    return _converter.structure(data, KIND_TO_REF_CLASS[kind])


# ---------------------------------------------------------------------------
# Domain <-> ORM mapping helpers
# ---------------------------------------------------------------------------


def _fact_to_row(fact: Fact) -> _FactRow:
    return _FactRow(
        id=fact.id,
        type=fact.type,
        subject_type=fact.subject.type.value,
        subject_id=fact.subject.id,
        predicate=fact.predicate,
        object_type=fact.object.type.value if fact.object else None,
        object_id=fact.object.id if fact.object else None,
        value=fact.value,
        provenance=fact.provenance,
        confidence=fact.confidence,
        source_analyzer=fact.source_analyzer,
        created_at=fact.created_at,
        schema_version=fact.schema_version,
        run_id=fact.run_id,
        evidence_rows=[
            _EvidenceRow(
                kind=ev.kind,
                ref=dataclasses.asdict(ev.ref),
                source_analyzer=ev.source_analyzer,
                retrieved_at=ev.retrieved_at,
            )
            for ev in fact.evidence
        ],
    )


def _row_to_fact(row: _FactRow) -> Fact:
    evidence = tuple(
        Evidence(
            kind=ev.kind,
            ref=_structure_ref(ev.kind, ev.ref),
            source_analyzer=ev.source_analyzer,
            retrieved_at=ev.retrieved_at,
        )
        for ev in row.evidence_rows
    )
    return Fact(
        id=row.id,
        type=row.type,
        subject=EntityRef(type=EntityType(row.subject_type), id=row.subject_id),
        predicate=row.predicate,
        object=EntityRef(type=EntityType(row.object_type), id=row.object_id) if row.object_type else None,
        value=row.value,
        evidence=evidence,
        provenance=row.provenance,
        confidence=row.confidence,
        source_analyzer=row.source_analyzer,
        created_at=row.created_at,
        schema_version=row.schema_version,
        run_id=row.run_id,
    )


def _entity_to_row(entity: Entity) -> _EntityRow:
    return _EntityRow(
        type=entity.type.value,
        id=entity.id,
        attributes=entity.attributes,
        repository_id=entity.repository_id,
        schema_version=SCHEMA_VERSION,
    )


def _row_to_entity(row: _EntityRow) -> Entity:
    return Entity(
        type=EntityType(row.type),
        id=row.id,
        attributes=row.attributes,
        repository_id=row.repository_id,
    )


# ---------------------------------------------------------------------------
# Public store
# ---------------------------------------------------------------------------


class FactStore:
    """Append-only SQLite store for Fact and Entity records."""

    def __init__(self, path: Path) -> None:
        self._engine = create_engine(f"sqlite:///{path}")
        _Base.metadata.create_all(self._engine)
        self._Session = sessionmaker(bind=self._engine)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._Session() as session:
            row = session.get(_SchemaMetaRow, "schema_version")
            if row is None:
                session.add(_SchemaMetaRow(key="schema_version", value=SCHEMA_VERSION))
                session.commit()
            elif row.value != SCHEMA_VERSION:
                raise SchemaVersionError(
                    f"Store schema version {row.value!r} != code version {SCHEMA_VERSION!r}; "
                    "refusing to open. Migrate or delete the database."
                )

    def close(self) -> None:
        self._engine.dispose()

    def insert_facts(self, facts: Sequence[Fact]) -> None:
        with self._Session() as session:
            session.add_all(_fact_to_row(f) for f in facts)
            session.commit()

    def insert_entities(self, entities: Sequence[Entity]) -> None:
        with self._Session() as session:
            for entity in entities:
                session.merge(_entity_to_row(entity))
            session.commit()

    def query_facts(
        self,
        *,
        type: str | None = None,
        subject: EntityRef | None = None,
        run_id: str | None = None,
        provenance: str | None = None,
    ) -> Iterator[Fact]:
        stmt = select(_FactRow).order_by(_FactRow.created_at.asc(), _FactRow.id.asc())
        if type is not None:
            stmt = stmt.where(_FactRow.type == type)
        if subject is not None:
            stmt = stmt.where(
                _FactRow.subject_type == subject.type.value,
                _FactRow.subject_id == subject.id,
            )
        if run_id is not None:
            stmt = stmt.where(_FactRow.run_id == run_id)
        if provenance is not None:
            stmt = stmt.where(_FactRow.provenance == provenance)

        with self._Session() as session:
            rows = session.scalars(stmt).all()
            return iter([_row_to_fact(r) for r in rows])

    def latest_run_id(self, type: str | None = None) -> str | None:
        """The run_id of the most recently created fact (optionally of `type`), or None if none."""
        stmt = select(_FactRow.run_id)
        if type is not None:
            stmt = stmt.where(_FactRow.type == type)
        stmt = stmt.order_by(_FactRow.created_at.desc(), _FactRow.id.desc()).limit(1)
        with self._Session() as session:
            return session.scalars(stmt).first()

    def run_id_with(self, type: str, preferred: str | None) -> str | None:
        """`preferred` if it holds facts of `type`, else the latest run that does (None if no run does).

        Lets a stage run in isolation (`--only domain`) consume the most recent upstream facts
        instead of finding nothing under its own fresh run_id.
        """
        if preferred is not None:
            stmt = select(_FactRow.id).where(_FactRow.type == type, _FactRow.run_id == preferred).limit(1)
            with self._Session() as session:
                if session.scalars(stmt).first() is not None:
                    return preferred
        return self.latest_run_id(type=type)

    def find_subject_id(
        self, subject_type: EntityType, name_or_path: str, run_id: str | None = None
    ) -> str | None:
        """First subject id (of `subject_type`, optionally within `run_id`) equal to or ending
        in `/name_or_path`, case-insensitive. Exact matches win; ties break alphabetically."""
        lower = name_or_path.lower()
        sid = func.lower(_FactRow.subject_id)
        stmt = select(_FactRow.subject_id).where(
            _FactRow.subject_type == subject_type.value,
            or_(sid == lower, func.substr(sid, -(len(lower) + 1)) == "/" + lower),
        )
        if run_id is not None:
            stmt = stmt.where(_FactRow.run_id == run_id)
        stmt = stmt.distinct().order_by((sid != lower), _FactRow.subject_id).limit(1)
        with self._Session() as session:
            return session.scalars(stmt).first()

    def fact_exists(self, fact_id: str) -> bool:
        with self._Session() as session:
            return session.get(_FactRow, fact_id) is not None

    def get_entity(self, ref: EntityRef) -> Entity | None:
        with self._Session() as session:
            row = session.get(_EntityRow, (ref.type.value, ref.id))
            return _row_to_entity(row) if row else None

    def delete_run(self, run_id: str) -> None:
        """Remove all facts (and their evidence) for a run_id. Test/debug only."""
        with self._Session() as session:
            rows = session.scalars(
                select(_FactRow).where(_FactRow.run_id == run_id)
            ).all()
            for row in rows:
                session.delete(row)
            session.commit()
