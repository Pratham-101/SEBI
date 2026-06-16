"""Lightweight SQLite column migrations for development."""

from sqlalchemy import inspect, text

from app.core.database import engine


def migrate_sqlite_columns() -> None:
    """Add new columns to existing SQLite tables without Alembic."""
    if not str(engine.url).startswith("sqlite"):
        return

    inspector = inspect(engine)
    additions = {
        "analysis_results": [
            ("teams_json", "TEXT"),
            ("deadlines_json", "TEXT"),
            ("action_items_json", "TEXT"),
            ("risk_score", "FLOAT"),
            ("escalation_state", "VARCHAR(32)"),
            ("routing_json", "TEXT"),
            ("related_json", "TEXT"),
        ],
        "tickets": [
            ("devrev_group_id", "VARCHAR(256)"),
            ("assigned_team", "VARCHAR(128)"),
            ("assignee_user_id", "VARCHAR(256)"),
            ("assignee_name", "VARCHAR(128)"),
            ("assignment_rationale", "TEXT"),
            ("subtask_ids_json", "TEXT"),
        ],
        "notifications": [
            ("regulator_code", "VARCHAR(16) DEFAULT 'SEBI'"),
        ],
    }

    with engine.connect() as conn:
        for table, cols in additions.items():
            if table not in inspector.get_table_names():
                continue
            existing = {c["name"] for c in inspector.get_columns(table)}
            for col_name, col_type in cols:
                if col_name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
        conn.commit()
