"""add_audit_sla_notifications

Revision ID: 7ee27e8b28d5
Revises: 3b474303440b
Create Date: 2026-09-14 15:32:25.970632

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7ee27e8b28d5'
down_revision: Union[str, None] = '3b474303440b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:

    # ── 1. audit_logs table (append-only compliance log) ─────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id          SERIAL PRIMARY KEY,
            user_id     INTEGER REFERENCES users(id),
            action      VARCHAR NOT NULL,
            entity_type VARCHAR NOT NULL,
            entity_id   INTEGER,
            old_value   JSON,
            new_value   JSON,
            ip_address  VARCHAR,
            description TEXT,
            created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_id          ON audit_logs (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_action      ON audit_logs (action)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_type ON audit_logs (entity_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_entity_id   ON audit_logs (entity_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at  ON audit_logs (created_at)")

    # ── 2. notifications table ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER NOT NULL REFERENCES users(id),
            request_id INTEGER REFERENCES requests(id),
            subject    VARCHAR NOT NULL,
            body       TEXT NOT NULL,
            is_read    BOOLEAN NOT NULL DEFAULT false,
            sent_at    TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_id         ON notifications (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_user_id    ON notifications (user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_notifications_request_id ON notifications (request_id)")

    # ── 3. SLA columns on request_types and requests ──────────────────────────
    op.execute("ALTER TABLE request_types ADD COLUMN IF NOT EXISTS sla_hours INTEGER")
    op.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS sla_deadline  TIMESTAMP WITH TIME ZONE")
    op.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS sla_breached  BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE requests ADD COLUMN IF NOT EXISTS escalated_at  TIMESTAMP WITH TIME ZONE")

    # ── 4. Full-text search vector on requests ────────────────────────────────
    # Add a tsvector column, then a trigger to keep it updated, then a GIN index.
    op.execute("""
        ALTER TABLE requests
        ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('english',
                coalesce(title, '') || ' ' || coalesce(description, '')
            )
        ) STORED
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_requests_search_vector
        ON requests USING GIN (search_vector)
    """)

    # ── 5. Seed SLA hours on existing request types ───────────────────────────
    # Standard reports = 72 h, urgent/loan types = 24 h
    op.execute("""
        UPDATE request_types SET sla_hours = 24
        WHERE name IN ('Loan Portfolio Report', 'Custom Data Extract')
    """)
    op.execute("""
        UPDATE request_types SET sla_hours = 72
        WHERE name IN (
            'Daily Transaction Report',
            'Monthly Performance Report',
            'Branch Summary Report'
        )
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_requests_search_vector")
    op.execute("ALTER TABLE requests DROP COLUMN IF EXISTS search_vector")

    op.drop_column('requests', 'escalated_at')
    op.drop_column('requests', 'sla_breached')
    op.drop_column('requests', 'sla_deadline')
    op.drop_column('request_types', 'sla_hours')

    op.drop_index('ix_notifications_request_id', table_name='notifications')
    op.drop_index('ix_notifications_user_id',    table_name='notifications')
    op.drop_index('ix_notifications_id',         table_name='notifications')
    op.drop_table('notifications')

    op.drop_index('ix_audit_logs_created_at',  table_name='audit_logs')
    op.drop_index('ix_audit_logs_entity_id',   table_name='audit_logs')
    op.drop_index('ix_audit_logs_entity_type', table_name='audit_logs')
    op.drop_index('ix_audit_logs_action',      table_name='audit_logs')
    op.drop_index('ix_audit_logs_id',          table_name='audit_logs')
    op.drop_table('audit_logs')
