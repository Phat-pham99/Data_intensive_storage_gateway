"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-18 00:00:00

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENUM_DEFINITIONS: dict[str, tuple[str, ...]] = {
    "storage_class": (
        "STANDARD",
        "STANDARD_IA",
        "GLACIER_IR",
        "GLACIER",
        "DEEP_ARCHIVE",
    ),
    "lifecycle_state": (
        "CREATED",
        "ACTIVE",
        "ARCHIVE_REQUESTED",
        "ARCHIVING",
        "ARCHIVED",
        "RESTORE_REQUESTED",
        "RESTORING",
        "RESTORED",
        "FAILED",
    ),
    "job_type": ("ARCHIVE", "RESTORE"),
    "job_status": ("PENDING", "RUNNING", "SUCCEEDED", "FAILED"),
}


def _column_enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUM_DEFINITIONS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUM_DEFINITIONS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "objects",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("bucket", sa.String(length=255), nullable=False),
        sa.Column("key", sa.String(length=1024), nullable=False),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "storage_class",
            _column_enum("storage_class"),
            nullable=False,
            server_default=sa.text("'STANDARD'"),
        ),
        sa.Column(
            "lifecycle_state",
            _column_enum("lifecycle_state"),
            nullable=False,
            server_default=sa.text("'CREATED'"),
        ),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.PrimaryKeyConstraint("id", name="pk_objects"),
        sa.UniqueConstraint("bucket", "key", name="uq_objects_bucket_key"),
    )

    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_policies"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("job_type", _column_enum("job_type"), nullable=False),
        sa.Column(
            "status",
            _column_enum("job_status"),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_jobs"),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            name="fk_jobs_object_id_objects",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_jobs_idempotency_key"),
    )

    op.create_table(
        "folder_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("prefix", sa.String(length=1024), nullable=False),
        sa.Column(
            "status",
            _column_enum("job_status"),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),
        sa.Column("total_objects", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completed_objects", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("failed_objects", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.PrimaryKeyConstraint("id", name="pk_folder_jobs"),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("previous_state", _column_enum("lifecycle_state"), nullable=True),
        sa.Column("new_state", _column_enum("lifecycle_state"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
        sa.ForeignKeyConstraint(
            ["object_id"],
            ["objects.id"],
            name="fk_audit_events_object_id_objects",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_audit_events_job_id_jobs",
            ondelete="SET NULL",
        ),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("folder_jobs")
    op.drop_table("jobs")
    op.drop_table("policies")
    op.drop_table("objects")
    for name in ENUM_DEFINITIONS:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
