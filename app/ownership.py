"""Ownership checks. Every private record lookup goes through these helpers."""
from flask import abort

from .db import get_db

_TABLES = {"subjects", "tasks", "notes", "flashcards"}


def owned_or_404(table, row_id, user_id):
    """Return the row only if it belongs to `user_id`; otherwise 404 (no existence leak)."""
    if table not in _TABLES:  # table names are fixed in code, never user input
        raise ValueError("unknown table")
    row = get_db().execute(
        f"SELECT * FROM {table} WHERE id = ? AND user_id = ?", (row_id, user_id)
    ).fetchone()
    if row is None:
        abort(404)
    return row


def user_subjects(user_id):
    return get_db().execute(
        "SELECT id, name, color FROM subjects WHERE user_id = ? ORDER BY name COLLATE NOCASE",
        (user_id,),
    ).fetchall()


def resolve_subject(raw, user_id):
    """Form value -> (subject_id or None, ok). A foreign/unknown id is rejected."""
    raw = (raw or "").strip()
    if not raw:
        return None, True
    if not raw.isdigit():
        return None, False
    row = get_db().execute(
        "SELECT id FROM subjects WHERE id = ? AND user_id = ?", (int(raw), user_id)
    ).fetchone()
    return (row["id"], True) if row else (None, False)
