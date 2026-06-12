"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-06-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")

    op.create_table(
        "users",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("email", postgresql.CITEXT(), nullable=False, unique=True),
        sa.Column("name", sa.String(255)),
        sa.Column("hashed_password", sa.String(255)),
        sa.Column("avatar_url", sa.String(1024)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "brand_profile",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("brand_name", sa.String(255), server_default="Dream_Grow"),
        sa.Column("target_audience", sa.Text()),
        sa.Column("tone_notes", sa.Text()),
        sa.Column("banned_phrases", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("required_ending", sa.Text()),
        sa.Column("brand_signature", sa.String(255)),
        sa.Column("categories", postgresql.JSONB(), server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "contents",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("category", sa.String(64)),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("body_md", sa.Text(), nullable=False, server_default=""),
        sa.Column("ai_original_md", sa.Text()),
        sa.Column("frontmatter", postgresql.JSONB(), server_default="{}"),
        sa.Column("generated_by_model", sa.String(64)),
        sa.Column("created_by", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_contents_status_channel", "contents", ["status", "channel"])
    op.create_index("ix_contents_category", "contents", ["category"])
    op.create_index("ix_contents_created_at", "contents", ["created_at"])
    op.execute("CREATE INDEX ix_contents_frontmatter ON contents USING GIN (frontmatter)")

    op.create_table(
        "content_versions",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("content_id", sa.String(26), sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("body_md", sa.Text(), nullable=False),
        sa.Column("edit_summary", sa.Text()),
        sa.Column("edited_by", sa.String(26), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("content_id", "version_no", name="uq_content_versions"),
    )

    op.create_table(
        "schedules",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("content_id", sa.String(26), sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Seoul"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("attempt_count", sa.Integer(), server_default="0"),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_schedules_status_at", "schedules", ["status", "scheduled_at"])
    op.create_index("ix_schedules_at", "schedules", ["scheduled_at"])

    op.create_table(
        "publish_results",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("content_id", sa.String(26), sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("external_id", sa.String(255)),
        sa.Column("external_url", sa.Text()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_publish_results_channel_at", "publish_results", ["channel", "published_at"])

    op.create_table(
        "lead_magnets",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("content_id", sa.String(26), sa.ForeignKey("contents.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("pdf_path", sa.Text()),
        sa.Column("pdf_size_bytes", sa.Integer(), server_default="0"),
        sa.Column("download_count", sa.Integer(), server_default="0"),
        sa.Column("public_token", sa.String(64), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("content_id", sa.String(26), sa.ForeignKey("contents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("views", sa.Integer(), server_default="0"),
        sa.Column("likes", sa.Integer(), server_default="0"),
        sa.Column("comments", sa.Integer(), server_default="0"),
        sa.Column("shares", sa.Integer(), server_default="0"),
        sa.Column("reach", sa.Integer(), server_default="0"),
        sa.Column("raw", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_analytics_content_at", "analytics_snapshots", ["content_id", "captured_at"])

    op.create_table(
        "learning_patterns",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("pattern_type", sa.String(64)),
        sa.Column("summary", sa.Text()),
        sa.Column("examples", postgresql.JSONB(), server_default="[]"),
        sa.Column("source", sa.String(32)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_learning_channel_at", "learning_patterns", ["channel", "created_at"])

    op.create_table(
        "integration_credentials",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("provider", sa.String(32), unique=True, nullable=False),
        sa.Column("encrypted_payload", sa.LargeBinary(), nullable=False),
        sa.Column("status", sa.String(32), server_default="ok"),
        sa.Column("meta", postgresql.JSONB(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(26), primary_key=True),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), server_default="{}"),
        sa.Column("status", sa.String(32), nullable=False, server_default="queued"),
        sa.Column("result", postgresql.JSONB(), server_default="{}"),
        sa.Column("error", sa.Text()),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_jobs_status_at", "jobs", ["status", "created_at"])


def downgrade() -> None:
    for tbl in [
        "jobs", "integration_credentials", "learning_patterns",
        "analytics_snapshots", "lead_magnets", "publish_results",
        "schedules", "content_versions", "contents", "brand_profile", "users",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
