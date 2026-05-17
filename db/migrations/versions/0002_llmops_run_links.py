"""add llmops run links"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0002_llmops_run_links"
down_revision = "0001_initial_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llmops_run_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dq_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_system", sa.String(length=32), nullable=False),
        sa.Column("external_run_id", sa.String(length=255), nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_name", sa.String(length=255), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"]),
        sa.ForeignKeyConstraint(["dq_run_id"], ["dq_runs.id"]),
    )
    op.create_index("ix_llmops_run_links_dataset_id", "llmops_run_links", ["dataset_id"])
    op.create_index("ix_llmops_run_links_dataset_version_id", "llmops_run_links", ["dataset_version_id"])
    op.create_index("ix_llmops_run_links_dq_run_id", "llmops_run_links", ["dq_run_id"])


def downgrade() -> None:
    op.drop_index("ix_llmops_run_links_dq_run_id", table_name="llmops_run_links")
    op.drop_index("ix_llmops_run_links_dataset_version_id", table_name="llmops_run_links")
    op.drop_index("ix_llmops_run_links_dataset_id", table_name="llmops_run_links")
    op.drop_table("llmops_run_links")
