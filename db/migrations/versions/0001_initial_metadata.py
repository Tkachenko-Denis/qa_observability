"""initial metadata schema"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0001_initial_metadata"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "dataset_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("location_uri", sa.String(length=512), nullable=True),
        sa.Column("event_time_min", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_time_max", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["baseline_id"], ["dataset_versions.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
    )
    op.create_index("ix_dataset_versions_dataset_id", "dataset_versions", ["dataset_id"])
    op.create_table(
        "dq_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("hard_gate_result", sa.String(length=16), nullable=False),
        sa.Column("soft_gate_result", sa.String(length=16), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["baseline_id"], ["dataset_versions.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"]),
    )
    op.create_index("ix_dq_runs_dataset_id", "dq_runs", ["dataset_id"])
    op.create_index("ix_dq_runs_dataset_version_id", "dq_runs", ["dataset_version_id"])
    op.create_table(
        "dq_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("dq_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("metric_value", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("event_time_min", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_time_max", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["baseline_id"], ["dataset_versions.id"]),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"]),
        sa.ForeignKeyConstraint(["dq_run_id"], ["dq_runs.id"]),
    )
    op.create_index("ix_dq_metrics_dataset_id", "dq_metrics", ["dataset_id"])
    op.create_index("ix_dq_metrics_dataset_version_id", "dq_metrics", ["dataset_version_id"])
    op.create_index("ix_dq_metrics_dq_run_id", "dq_metrics", ["dq_run_id"])
    op.create_table(
        "dq_alert_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("comparator", sa.String(length=16), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
    )
    op.create_index("ix_dq_alert_rules_dataset_id", "dq_alert_rules", ["dataset_id"])
    op.create_table(
        "dq_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("dq_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("event_time_min", sa.DateTime(timezone=True), nullable=True),
        sa.Column("event_time_max", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"]),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["dataset_versions.id"]),
        sa.ForeignKeyConstraint(["dq_run_id"], ["dq_runs.id"]),
    )
    op.create_index("ix_dq_events_dataset_id", "dq_events", ["dataset_id"])
    op.create_index("ix_dq_events_dataset_version_id", "dq_events", ["dataset_version_id"])
    op.create_index("ix_dq_events_dq_run_id", "dq_events", ["dq_run_id"])


def downgrade() -> None:
    op.drop_index("ix_dq_events_dq_run_id", table_name="dq_events")
    op.drop_index("ix_dq_events_dataset_version_id", table_name="dq_events")
    op.drop_index("ix_dq_events_dataset_id", table_name="dq_events")
    op.drop_table("dq_events")
    op.drop_index("ix_dq_alert_rules_dataset_id", table_name="dq_alert_rules")
    op.drop_table("dq_alert_rules")
    op.drop_index("ix_dq_metrics_dq_run_id", table_name="dq_metrics")
    op.drop_index("ix_dq_metrics_dataset_version_id", table_name="dq_metrics")
    op.drop_index("ix_dq_metrics_dataset_id", table_name="dq_metrics")
    op.drop_table("dq_metrics")
    op.drop_index("ix_dq_runs_dataset_version_id", table_name="dq_runs")
    op.drop_index("ix_dq_runs_dataset_id", table_name="dq_runs")
    op.drop_table("dq_runs")
    op.drop_index("ix_dataset_versions_dataset_id", table_name="dataset_versions")
    op.drop_table("dataset_versions")
    op.drop_table("datasets")
