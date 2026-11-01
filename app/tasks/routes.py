from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..db import get_db
from ..helpers import relative_due, user_today
from ..ownership import owned_or_404, resolve_subject, user_subjects
from ..security import (clean_text, like_pattern, login_required, parse_date, safe_next)

bp = Blueprint("tasks", __name__)

PRIORITIES = ("Low", "Medium", "High")
STATUSES = [("all", "All"), ("pending", "Pending"), ("completed", "Completed"), ("overdue", "Overdue")]
SORTS = {
    "deadline": ("Deadline", "t.completed ASC, t.due_date IS NULL, t.due_date ASC, t.id DESC"),
    "priority": ("Priority", "t.completed ASC, CASE t.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, "
                             "t.due_date IS NULL, t.due_date ASC, t.id DESC"),
    "newest": ("Newest", "t.id DESC"),
}


@bp.route("/")
@login_required
def index():
    db, uid, today = get_db(), g.user["id"], user_today()
    iso = today.isoformat()
    status = request.args.get("status", "all")
    status = status if status in dict(STATUSES) else "all"
    sort = request.args.get("sort", "deadline")
    sort = sort if sort in SORTS else "deadline"
    q = clean_text(request.args.get("q"), 100)
    subjects = user_subjects(uid)
    raw_subject = request.args.get("subject", "")
    subject = None
    if raw_subject == "none":
        subject = "none"
    elif raw_subject.isdigit() and int(raw_subject) in {s["id"] for s in subjects}:
        subject = int(raw_subject)

    sql = ("SELECT t.*, s.name AS subject_name, s.color AS subject_color FROM tasks t "
           "LEFT JOIN subjects s ON s.id=t.subject_id AND s.user_id=t.user_id WHERE t.user_id=?")
    params = [uid]
    if status == "pending":
        sql += " AND t.completed=0"
    elif status == "completed":
        sql += " AND t.completed=1"
    elif status == "overdue":
        sql += " AND t.completed=0 AND t.due_date IS NOT NULL AND t.due_date < ?"
        params.append(iso)
    if subject == "none":
        sql += " AND t.subject_id IS NULL"
    elif subject is not None:
        sql += " AND t.subject_id=?"
        params.append(subject)
    if q:
        sql += " AND (t.title LIKE ? ESCAPE '\\' OR t.description LIKE ? ESCAPE '\\')"
        params += [like_pattern(q)] * 2
    sql += " ORDER BY " + SORTS[sort][1]  # whitelisted fragment
    tasks = []
    for row in db.execute(sql, params).fetchall():
        item = dict(row)
        item["overdue"] = bool(not row["completed"] and row["due_date"] and row["due_date"] < iso)
        item["due_text"] = relative_due(row["due_date"], today) if not row["completed"] else ""
        tasks.append(item)

    counts = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(completed=0),0), COALESCE(SUM(completed=1),0), "
        "COALESCE(SUM(completed=0 AND due_date IS NOT NULL AND due_date < ?),0) "
        "FROM tasks WHERE user_id=?", (iso, uid)).fetchone()
    return render_template(
        "tasks/index.html", tasks=tasks, subjects=subjects, status=status, sort=sort, q=q,
        subject=subject, statuses=STATUSES, sorts=SORTS,
        counts={"all": counts[0], "pending": counts[1], "completed": counts[2], "overdue": counts[3]},
        filtered=bool(q or subject is not None or status != "all"))


def _read_form(uid):
    title = clean_text(request.form.get("title"), 200)
    description = clean_text(request.form.get("description"), 2000, multiline=True)
    priority = request.form.get("priority", "Medium")
    raw_due = request.form.get("due_date", "").strip()
    due = parse_date(raw_due)
    subject_id, subject_ok = resolve_subject(request.form.get("subject_id"), uid)
    errors = []
    if not title:
        errors.append("Give the assignment a title.")
    if priority not in PRIORITIES:
        errors.append("Choose a priority.")
    if raw_due and not due:
        errors.append("That deadline isn't a valid date.")
    if not subject_ok:
        errors.append("Choose one of your own subjects.")
    form = {"title": title, "description": description, "priority": priority if priority in PRIORITIES else "Medium",
            "due_date": due or "", "subject_id": subject_id}
    return form, errors


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    uid = g.user["id"]
    form = {"title": "", "description": "", "priority": "Medium", "due_date": "",
            "subject_id": request.args.get("subject", type=int)}
    if request.method == "POST":
        form, errors = _read_form(uid)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db = get_db()
            db.execute(
                "INSERT INTO tasks (user_id, title, description, subject_id, due_date, priority, updated_at) "
                "VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                (uid, form["title"], form["description"], form["subject_id"], form["due_date"] or None, form["priority"]))
            db.commit()
            flash("Assignment added.", "success")
            return redirect(url_for("tasks.index"))
    return render_template("tasks/form.html", form=form, task=None, subjects=user_subjects(uid), priorities=PRIORITIES)


@bp.route("/<int:task_id>/edit", methods=["GET", "POST"])
@login_required
def edit(task_id):
    uid = g.user["id"]
    task = owned_or_404("tasks", task_id, uid)
    form = {"title": task["title"], "description": task["description"], "priority": task["priority"],
            "due_date": task["due_date"] or "", "subject_id": task["subject_id"]}
    if request.method == "POST":
        form, errors = _read_form(uid)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db = get_db()
            db.execute(
                "UPDATE tasks SET title=?, description=?, subject_id=?, due_date=?, priority=?, "
                "updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
                (form["title"], form["description"], form["subject_id"], form["due_date"] or None,
                 form["priority"], task_id, uid))
            db.commit()
            flash("Assignment updated.", "success")
            return redirect(url_for("tasks.index"))
    return render_template("tasks/form.html", form=form, task=task, subjects=user_subjects(uid), priorities=PRIORITIES)


@bp.route("/<int:task_id>/toggle", methods=["POST"])
@login_required
def toggle(task_id):
    uid = g.user["id"]
    owned_or_404("tasks", task_id, uid)
    db = get_db()
    db.execute(
        "UPDATE tasks SET completed = 1 - completed, "
        "completed_at = CASE WHEN completed = 0 THEN CURRENT_TIMESTAMP ELSE NULL END "
        "WHERE id=? AND user_id=?", (task_id, uid))
    db.commit()
    return redirect(safe_next(request.form.get("next"), url_for("tasks.index")))


@bp.route("/<int:task_id>/delete", methods=["POST"])
@login_required
def delete(task_id):
    uid = g.user["id"]
    owned_or_404("tasks", task_id, uid)
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (task_id, uid))
    db.commit()
    flash("Assignment deleted.", "success")
    return redirect(safe_next(request.form.get("next"), url_for("tasks.index")))
