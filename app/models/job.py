from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.enums import JobStatus, JobType
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin, enum_column


class Job(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An asynchronous archive/restore operation for a single object."""

    __tablename__ = "jobs"

    job_type: Mapped[JobType] = mapped_column(enum_column(JobType, "job_type"), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        enum_column(JobStatus, "job_status"),
        nullable=False,
        default=JobStatus.PENDING,
    )
    object_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("objects.id", ondelete="CASCADE"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    object = relationship("StorageObject", lazy="joined")

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"Job(id={self.id!r}, type={self.job_type!r}, status={self.status!r})"


class FolderJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Aggregate tracking for a prefix-scoped batch operation."""

    __tablename__ = "folder_jobs"

    prefix: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        enum_column(JobStatus, "job_status"),
        nullable=False,
        default=JobStatus.PENDING,
    )
    total_objects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_objects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_objects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"FolderJob(id={self.id!r}, prefix={self.prefix!r}, status={self.status!r})"
