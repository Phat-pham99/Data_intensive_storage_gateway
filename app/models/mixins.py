from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Integer, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column


def enum_column(enum_cls: type[Enum], name: str) -> SAEnum:
    """Return a native PostgreSQL enum column type that stores enum values."""

    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda cls: [member.value for member in cls],
    )


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OptimisticLockMixin:
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
