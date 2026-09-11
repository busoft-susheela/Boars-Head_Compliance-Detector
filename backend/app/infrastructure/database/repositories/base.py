"""BaseRepository — generic CRUD foundation for all repositories.

CV components must NOT execute SQL directly.  They depend on repository
interfaces and receive concrete implementations via dependency injection.
"""
from __future__ import annotations

from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy.orm import Session

from backend.app.infrastructure.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Provides save / get / list operations for one ORM model type.

    Args:
        session: SQLAlchemy session for this unit of work.
        model:   The ORM model class managed by this repository.
    """

    def __init__(self, session: Session, model: type[ModelT]) -> None:
        self._session = session
        self._model = model

    def save(self, instance: ModelT) -> ModelT:
        """Persist a new or detached instance (does NOT commit)."""
        self._session.add(instance)
        self._session.flush()
        return instance

    def get(self, id: UUID) -> ModelT | None:
        """Retrieve by primary key UUID."""
        return self._session.get(self._model, id)

    def list(self, **filters) -> list[ModelT]:
        """Return all rows matching the given column=value filters."""
        q = self._session.query(self._model)
        for attr, value in filters.items():
            q = q.filter(getattr(self._model, attr) == value)
        return q.all()
