"""add_ai_fields

Revision ID: c820633a1741
Revises: 4631a55dea8e
Create Date: 2026-09-15 16:17:29.114143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c820633a1741'
down_revision: Union[str, None] = '4631a55dea8e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # AI / ML columns on requests — all nullable so existing rows are unaffected
    op.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS ai_suggested_type_id    INTEGER REFERENCES request_types(id)")
    op.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS ai_type_confidence      FLOAT")
    op.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS ai_suggested_officer_id INTEGER REFERENCES users(id)")
    op.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS ai_officer_score        FLOAT")
    op.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS ai_anomaly_flagged      BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS ai_anomaly_details      JSON")
    op.execute("CREATE INDEX IF NOT EXISTS ix_requests_ai_flagged ON requests (ai_anomaly_flagged)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_requests_ai_flagged")
    op.execute("ALTER TABLE requests DROP COLUMN IF EXISTS ai_anomaly_details")
    op.execute("ALTER TABLE requests DROP COLUMN IF EXISTS ai_anomaly_flagged")
    op.execute("ALTER TABLE requests DROP COLUMN IF EXISTS ai_officer_score")
    op.execute("ALTER TABLE requests DROP COLUMN IF EXISTS ai_suggested_officer_id")
    op.execute("ALTER TABLE requests DROP COLUMN IF EXISTS ai_type_confidence")
    op.execute("ALTER TABLE requests DROP COLUMN IF EXISTS ai_suggested_type_id")
