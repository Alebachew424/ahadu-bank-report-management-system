"""
Migrate all data from SQLite (test.db) to PostgreSQL (report_management).

Copies every table in FK-safe order, preserving all IDs and resetting
PostgreSQL sequences so auto-increment continues from the right value.

Run from backend/ directory:
    python scripts/sqlite_to_postgres.py
"""
import sys
import os
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
import psycopg2.extras

SQLITE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", "test.db")
# If running from inside backend/ already, adjust:
if not os.path.exists(SQLITE_PATH):
    SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test.db")

PG_DSN = "host=localhost port=5432 user=postgres password=postgres dbname=report_management"

# Tables in insertion order (parents before children, circular FK handled last)
# departments.manager_id → users.id  (circular with users.department_id)
# Strategy: insert departments with manager_id=NULL first, insert users, then fix manager_id
# Columns that are boolean in the SQLAlchemy models but stored as 0/1 in SQLite.
# Rather than hardcoding, we detect them from the PostgreSQL schema at runtime.
BOOLEAN_COLUMNS: dict[str, set] = {}  # filled in main() after PG connection


def load_boolean_columns(pg_cur):
    """Query information_schema to find all boolean columns in all tables."""
    pg_cur.execute("""
        SELECT table_name, column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND data_type = 'boolean'
    """)
    for table_name, col_name in pg_cur.fetchall():
        BOOLEAN_COLUMNS.setdefault(table_name, set()).add(col_name)
    print(f"  Detected boolean columns: {dict(BOOLEAN_COLUMNS)}")
    print()

TABLES_IN_ORDER = [
    "roles",
    "departments",       # inserted with manager_id=NULL first
    "users",
    "statuses",
    "request_types",
    "requests",
    "transitions",
    "attachments",
    "request_comments",
    "request_feedback",
]


def get_sqlite_rows(sqlite_cur, table):
    sqlite_cur.execute(f"SELECT * FROM {table}")
    cols = [d[0] for d in sqlite_cur.description]
    rows = sqlite_cur.fetchall()
    return cols, rows


def truncate_all(pg_cur):
    """Truncate all tables in reverse order, disabling FK checks temporarily."""
    print("  Truncating existing PostgreSQL data...")
    pg_cur.execute("SET session_replication_role = replica")  # disable FK checks
    for table in reversed(TABLES_IN_ORDER):
        pg_cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE")
    pg_cur.execute("SET session_replication_role = DEFAULT")


def cast_row(cols, row, table):
    """Convert SQLite integer booleans to Python bool for PostgreSQL."""
    bool_cols = BOOLEAN_COLUMNS.get(table, set())
    if not bool_cols:
        return tuple(row)
    result = []
    for col, val in zip(cols, row):
        if col in bool_cols and val is not None:
            result.append(bool(val))
        else:
            result.append(val)
    return tuple(result)


def copy_table(sqlite_cur, pg_cur, table, skip_columns=None):
    cols, rows = get_sqlite_rows(sqlite_cur, table)
    if not rows:
        print(f"  {table:<35} 0 rows (empty — skipping)")
        return 0

    if skip_columns:
        # Remove specified columns from insert
        col_indices = [i for i, c in enumerate(cols) if c not in skip_columns]
        insert_cols = [cols[i] for i in col_indices]
        rows = [tuple(cast_row([cols[i] for i in col_indices],
                               [row[i] for i in col_indices], table))
                for row in rows]
    else:
        insert_cols = cols
        rows = [cast_row(cols, row, table) for row in rows]

    placeholders = ", ".join(["%s"] * len(insert_cols))
    col_names    = ", ".join(insert_cols)
    sql          = f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})"

    # Disable FK checks for this session
    pg_cur.execute("SET session_replication_role = replica")
    psycopg2.extras.execute_batch(pg_cur, sql, rows, page_size=500)
    pg_cur.execute("SET session_replication_role = DEFAULT")

    print(f"  {table:<35} {len(rows)} rows copied")
    return len(rows)


def reset_sequence(pg_cur, table, id_col="id"):
    """Reset the PostgreSQL serial sequence to max(id) so future inserts don't conflict."""
    pg_cur.execute(f"SELECT MAX({id_col}) FROM {table}")
    max_id = pg_cur.fetchone()[0]
    if max_id is not None:
        seq_name = f"{table}_{id_col}_seq"
        pg_cur.execute(f"SELECT setval('{seq_name}', {max_id})")


def fix_departments_manager_id(sqlite_cur, pg_cur):
    """After users are inserted, patch departments.manager_id from SQLite."""
    sqlite_cur.execute("SELECT id, manager_id FROM departments WHERE manager_id IS NOT NULL")
    rows = sqlite_cur.fetchall()
    if not rows:
        return
    for dept_id, manager_id in rows:
        pg_cur.execute(
            "UPDATE departments SET manager_id = %s WHERE id = %s",
            (manager_id, dept_id)
        )
    print(f"  departments.manager_id       {len(rows)} links restored")


def main():
    if not os.path.exists(SQLITE_PATH):
        print(f"ERROR: SQLite file not found at {SQLITE_PATH}")
        sys.exit(1)

    print(f"Source : {SQLITE_PATH}")
    print(f"Target : PostgreSQL report_management @ localhost:5432")
    print()

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur  = sqlite_conn.cursor()

    pg_conn = psycopg2.connect(PG_DSN)
    pg_cur  = pg_conn.cursor()

    try:
        # Step 0: detect boolean columns from PG schema
        load_boolean_columns(pg_cur)

        # Step 1: clear existing PG data
        truncate_all(pg_cur)
        pg_conn.commit()

        # Step 2: copy roles first
        copy_table(sqlite_cur, pg_cur, "roles")

        # Step 3: copy departments WITHOUT manager_id (avoid FK violation — users don't exist yet)
        copy_table(sqlite_cur, pg_cur, "departments", skip_columns=["manager_id"])

        # Step 4: copy users (references roles + departments)
        copy_table(sqlite_cur, pg_cur, "users")

        # Step 5: fix departments.manager_id now that users exist
        fix_departments_manager_id(sqlite_cur, pg_cur)

        # Step 6: copy remaining tables
        for table in ["statuses", "request_types", "requests", "transitions",
                      "attachments", "request_comments", "request_feedback"]:
            copy_table(sqlite_cur, pg_cur, table)

        # Step 7: reset all sequences
        print()
        print("Resetting sequences...")
        for table in TABLES_IN_ORDER:
            reset_sequence(pg_cur, table)
            print(f"  {table}_id_seq reset")

        pg_conn.commit()
        print()
        print("Migration complete.")

    except Exception as e:
        pg_conn.rollback()
        print(f"\nERROR — rolled back: {e}")
        raise
    finally:
        sqlite_conn.close()
        pg_conn.close()


if __name__ == "__main__":
    main()
