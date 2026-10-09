"""add_recurring_schedules

Revision ID: 4631a55dea8e
Revises: 7ee27e8b28d5
Create Date: 2026-09-14 17:01:28.472039

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '4631a55dea8e'
down_revision: Union[str, None] = '7ee27e8b28d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS recurring_schedules (
            id                   SERIAL PRIMARY KEY,
            owner_id             INTEGER NOT NULL REFERENCES users(id),
            title                VARCHAR NOT NULL,
            description          TEXT,
            request_type_id      INTEGER NOT NULL REFERENCES request_types(id),
            priority             VARCHAR NOT NULL DEFAULT 'medium',
            due_in_hours         INTEGER NOT NULL DEFAULT 24,
            preferred_officer_id INTEGER REFERENCES users(id),
            completion_mode      VARCHAR NOT NULL DEFAULT 'require_feedback',
            frequency            VARCHAR NOT NULL,
            hour                 INTEGER NOT NULL DEFAULT 9,
            minute               INTEGER NOT NULL DEFAULT 0,
            day_of_week          INTEGER,
            day_of_month         INTEGER,
            is_active            BOOLEAN NOT NULL DEFAULT true,
            last_fired_at        TIMESTAMP WITH TIME ZONE,
            next_run_at          TIMESTAMP WITH TIME ZONE,
            total_fired          INTEGER NOT NULL DEFAULT 0,
            created_at           TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
            updated_at           TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_recurring_schedules_id       ON recurring_schedules (id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_recurring_schedules_owner_id ON recurring_schedules (owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_recurring_schedules_active   ON recurring_schedules (is_active)")


def downgrade() -> None:
    op.drop_index('ix_recurring_schedules_active',   table_name='recurring_schedules')
    op.drop_index('ix_recurring_schedules_owner_id', table_name='recurring_schedules')
    op.drop_index('ix_recurring_schedules_id',       table_name='recurring_schedules')
    op.drop_table('recurring_schedules')
