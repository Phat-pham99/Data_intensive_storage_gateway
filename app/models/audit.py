from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.enums import LifecycleState
from app.models.mixins import UUIDPrimaryKeyMixin, enum_column


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """Immutable record of a lifecycle state transition."""

    __tablename__ = "audit_events"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    object_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("objects.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    previous_state: Mapped[LifecycleState | None] = mapped_column(
        enum_column(LifecycleState, "lifecycle_state"), nullable=True
    )
    new_state: Mapped[LifecycleState] = mapped_column(
        enum_column(LifecycleState, "lifecycle_state"), nullable=False
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"AuditEvent(id={self.id!r}, {self.previous_state!r} -> {self.new_state!r})"
