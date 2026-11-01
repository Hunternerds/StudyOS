from datetime import timedelta

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..analytics import service
from ..db import get_db
from ..helpers import user_today
from ..ownership import owned_or_404
from ..security import clean_text, login_required, parse_color

bp = Blueprint("subjects", __name__)

PALETTE = ["#8b5cf6", "#6366f1", "#38bdf8", "#34d399", "#f472b6", "#fbbf24", "#fb7185", "#94a3b8"]

LIST_SQL = """
SELECT s.*,
  (SELECT COALESCE(SUM(duration),0) FROM study_sessions x
     WHERE x.user_id=s.user_id AND x.subject_id=s.id AND x.kind='focus') AS minutes,
  (SELECT COUNT(*) FROM tasks t WHERE t.user_id=s.user_id AND t.subject_id=s.id AND t.completed=0) AS pending,
  (SELECT COUNT(*) FROM notes n WHERE n.user_id=s.user_id AND n.subject_id=s.id) AS notes,
  (SELECT COUNT(*) FROM flashcards f WHERE f.user_id=s.user_id AND f.subject_id=s.id) AS cards
FROM subjects s WHERE s.user_id=? ORDER BY s.name COLLATE NOCASE
"""


@bp.route("/")
@login_required
def index():
    return render_template("subjects/index.html", subjects=get_db().execute(LIST_SQL, (g.user["id"],)).fetchall())


def _read_form():
    return (clean_text(request.form.get("name"), 60),
            clean_text(request.form.get("description"), 400, multiline=True),
            parse_color(request.form.get("color")))


def _name_taken(name, uid, exclude_id=None):
    row = get_db().execute(
        "SELECT id FROM subjects WHERE user_id=? AND name=? COLLATE NOCASE", (uid, name)).fetchone()
    return bool(row and row["id"] != exclude_id)


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    uid, form = g.user["id"], {"name": "", "description": "", "color": PALETTE[0]}
    if request.method == "POST":
        name, description, color = _read_form()
        form = {"name": name, "description": description, "color": color}
        if not name:
            flash("Give the subject a name.", "error")
        elif _name_taken(name, uid):
            flash("You already have a subject with that name.", "error")
        else:
            db = get_db()
            cur = db.execute(
                "INSERT INTO subjects (user_id, name, description, color) VALUES (?,?,?,?)",
                (uid, name, description, color))
            db.commit()
            flash("Subject created.", "success")
            return redirect(url_for("subjects.detail", subject_id=cur.lastrowid))
    return render_template("subjects/form.html", form=form, subject=None, palette=PALETTE)


@bp.route("/<int:subject_id>")
@login_required
def detail(subject_id):
    db, uid, today = get_db(), g.user["id"], user_today()
    subject = owned_or_404("subjects", subject_id, uid)
    one = lambda sql: db.execute(sql, (uid, subject_id)).fetchone()[0]  # noqa: E731
    stats = {
        "minutes": one("SELECT COALESCE(SUM(duration),0) FROM study_sessions "
                       "WHERE user_id=? AND subject_id=? AND kind='focus'"),
        "sessions": one("SELECT COUNT(*) FROM study_sessions WHERE user_id=? AND subject_id=? AND kind='focus'"),
        "pending": one("SELECT COUNT(*) FROM tasks WHERE user_id=? AND subject_id=? AND completed=0"),
        "done": one("SELECT COUNT(*) FROM tasks WHERE user_id=? AND subject_id=? AND completed=1"),
        "notes": one("SELECT COUNT(*) FROM notes WHERE user_id=? AND subject_id=?"),
        "cards": one("SELECT COUNT(*) FROM flashcards WHERE user_id=? AND subject_id=?"),
    }
    week = service.day_series(db, uid, today - timedelta(days=6), today, subject_id)
    sessions = service.recent_sessions(db, uid, 6, subject=subject_id)
    tasks = db.execute(
        "SELECT id, title, due_date, priority FROM tasks WHERE user_id=? AND subject_id=? AND completed=0 "
        "ORDER BY due_date IS NULL, due_date LIMIT 5", (uid, subject_id)).fetchall()
    return render_template("subjects/detail.html", subject=subject, stats=stats, week=week,
                           sessions=sessions, tasks=tasks)


@bp.route("/<int:subject_id>/edit", methods=["GET", "POST"])
@login_required
def edit(subject_id):
    uid = g.user["id"]
    subject = owned_or_404("subjects", subject_id, uid)
    form = {"name": subject["name"], "description": subject["description"], "color": subject["color"]}
    if request.method == "POST":
        name, description, color = _read_form()
        form = {"name": name, "description": description, "color": color}
        if not name:
            flash("Give the subject a name.", "error")
        elif _name_taken(name, uid, subject_id):
            flash("You already have a subject with that name.", "error")
        else:
            db = get_db()
            db.execute("UPDATE subjects SET name=?, description=?, color=? WHERE id=? AND user_id=?",
                       (name, description, color, subject_id, uid))
            db.commit()
            flash("Subject updated.", "success")
            return redirect(url_for("subjects.detail", subject_id=subject_id))
    return render_template("subjects/form.html", form=form, subject=subject, palette=PALETTE)


@bp.route("/<int:subject_id>/delete", methods=["POST"])
@login_required
def delete(subject_id):
    uid = g.user["id"]
    owned_or_404("subjects", subject_id, uid)
    db = get_db()
    db.execute("DELETE FROM subjects WHERE id=? AND user_id=?", (subject_id, uid))
    db.commit()
    flash("Subject deleted. Its tasks, notes, cards and sessions were kept as unassigned.", "success")
    return redirect(url_for("subjects.index"))
