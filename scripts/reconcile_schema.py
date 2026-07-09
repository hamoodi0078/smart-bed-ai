"""Add columns the ORM model declares but the live database is missing.

Dev databases in this project were often built by ``create_tables()``
(``Base.metadata.create_all``), which creates missing *tables* but never
ALTERs existing ones. When the model later gains a column, the table drifts —
the schema-drift the 2026-07-08 audit warned about. This script closes that
gap non-destructively: it only ADDs missing columns, never drops or alters
existing data.

Usage:
    python scripts/reconcile_schema.py            # reconcile configured DB
    python scripts/reconcile_schema.py --dry-run  # report only

DATABASE_URL is read from the environment / .env (via python-dotenv).
"""

from __future__ import annotations

import os
import sys

# Allow running as `python scripts/reconcile_schema.py` from the repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

from sqlalchemy import create_engine, inspect
from sqlalchemy.schema import CreateColumn

from database.models import Base


def _default_literal(column) -> str | None:
    """Return a SQL literal for a NOT NULL column's default so existing rows
    get a value when the column is added. Only handles scalar defaults."""
    default = column.default
    if default is None or not getattr(default, "is_scalar", False):
        return None
    value = default.arg
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return f"'{value}'"


def reconcile(dry_run: bool = False) -> int:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        print("DATABASE_URL is not set; refusing to guess. Set it and retry.")
        return 2

    engine = create_engine(url)
    dialect = engine.dialect
    inspector = inspect(engine)
    db_tables = set(inspector.get_table_names())

    added = 0
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in db_tables:
                print(f"! table '{table.name}' missing entirely — run migrations/create_tables first")
                continue
            live_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in live_cols:
                    continue
                col_sql = str(CreateColumn(column).compile(dialect=dialect)).strip()
                stmt = f'ALTER TABLE "{table.name}" ADD COLUMN {col_sql}'
                # A NOT NULL column can't be added to a populated table without
                # a default to backfill existing rows.
                if not column.nullable and column.server_default is None:
                    literal = _default_literal(column)
                    if literal is not None:
                        stmt += f" DEFAULT {literal}"
                    else:
                        # No usable default — add nullable so the ALTER succeeds;
                        # the app enforces the value going forward.
                        stmt = stmt.replace(" NOT NULL", "")
                if dry_run:
                    print(f"[dry-run] {stmt}")
                else:
                    conn.exec_driver_sql(stmt)
                    print(f"+ added {table.name}.{column.name}")
                added += 1

    if added == 0:
        print("Schema already matches the model — nothing to do.")
    else:
        print(f"{'Would add' if dry_run else 'Added'} {added} column(s).")
    return 0


if __name__ == "__main__":
    sys.exit(reconcile(dry_run="--dry-run" in sys.argv))
