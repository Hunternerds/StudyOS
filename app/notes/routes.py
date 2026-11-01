from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from ..db import get_db
from ..ownership import owned_or_404, resolve_subject, user_subjects
from ..security import clean_text, like_pattern, login_required, parse_int

bp = Blueprint("notes", __name__)

MAX_TITLE, MAX_CONTENT = 150, 100_000


@bp.route("/")
@login_required
def index():
    db, uid = get_db(), g.user["id"]
    q = clean_text(request.args.get("q"), 100)
    subjects = user_subjects(uid)
    raw = request.args.get("subject", "")
    subject = int(raw) if raw.isdigit() and int(raw) in {s["id"] for s in subjects} else None
    sql = ("SELECT n.id, n.title, n.updated_at, n.created_at, substr(n.content,1,160) AS preview, "
           "s.name AS subject_name, s.color AS subject_color FROM notes n "
           "LEFT JOIN subjects s ON s.id=n.subject_id AND s.user_id=n.user_id WHERE n.user_id=?")
    params = [uid]
    if subject is not None:
        sql += " AND n.subject_id=?"
        params.append(subject)
    if q:
        sql += " AND (n.title LIKE ? ESCAPE '\\' OR n.content LIKE ? ESCAPE '\\')"
        params += [like_pattern(q)] * 2
    sql += " ORDER BY n.updated_at DESC, n.id DESC LIMIT 200"
    return render_template("notes/index.html", notes=db.execute(sql, params).fetchall(),
                           subjects=subjects, q=q, subject=subject)


def _fields(source, uid):
    title = clean_text(source.get("title"), MAX_TITLE) or "Untitled note"
    content = clean_text(source.get("content"), MAX_CONTENT, multiline=True)
    subject_id, ok = resolve_subject(str(source.get("subject_id") or ""), uid)
    return title, content, subject_id, ok


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    uid = g.user["id"]
    if request.method == "POST":
        title, content, subject_id, ok = _fields(request.form, uid)
        if not ok:
            flash("Choose one of your own subjects.", "error")
        else:
            db = get_db()
            cur = db.execute("INSERT INTO notes (user_id, title, content, subject_id) VALUES (?,?,?,?)",
                             (uid, title, content, subject_id))
            db.commit()
            flash("Note saved.", "success")
            return redirect(url_for("notes.edit", note_id=cur.lastrowid))
    return render_template("notes/editor.html", note=None, subjects=user_subjects(uid),
                           preset_subject=request.args.get("subject", type=int))


@bp.route("/<int:note_id>", methods=["GET", "POST"])
@login_required
def edit(note_id):
    uid = g.user["id"]
    note = owned_or_404("notes", note_id, uid)
    if request.method == "POST":
        title, content, subject_id, ok = _fields(request.form, uid)
        if not ok:
            flash("Choose one of your own subjects.", "error")
        else:
            db = get_db()
            db.execute("UPDATE notes SET title=?, content=?, subject_id=?, updated_at=CURRENT_TIMESTAMP "
                       "WHERE id=? AND user_id=?", (title, content, subject_id, note_id, uid))
            db.commit()
            flash("Note saved.", "success")
            return redirect(url_for("notes.edit", note_id=note_id))
    return render_template("notes/editor.html", note=note, subjects=user_subjects(uid), preset_subject=None)


@bp.route("/autosave", methods=["POST"])
@login_required
def autosave():
    """JSON autosave. Creates the note on first save, then updates it."""
    uid, data = g.user["id"], request.get_json(silent=True) or {}
    title, content, subject_id, ok = _fields(data, uid)
    if not ok:
        return jsonify({"ok": False, "error": "Invalid subject."}), 400
    db = get_db()
    note_id = parse_int(data.get("id"), 1, 2**62)
    if note_id:
        owned_or_404("notes", note_id, uid)
        db.execute("UPDATE notes SET title=?, content=?, subject_id=?, updated_at=CURRENT_TIMESTAMP "
                   "WHERE id=? AND user_id=?", (title, content, subject_id, note_id, uid))
    else:
        if not content and not clean_text(data.get("title"), MAX_TITLE):
            return jsonify({"ok": True, "id": None, "skipped": True})
        note_id = db.execute("INSERT INTO notes (user_id, title, content, subject_id) VALUES (?,?,?,?)",
                             (uid, title, content, subject_id)).lastrowid
    db.commit()
    row = db.execute("SELECT updated_at FROM notes WHERE id=? AND user_id=?", (note_id, uid)).fetchone()
    return jsonify({"ok": True, "id": note_id, "updated_at": row["updated_at"],
                    "url": url_for("notes.edit", note_id=note_id)})


@bp.route("/<int:note_id>/delete", methods=["POST"])
@login_required
def delete(note_id):
    uid = g.user["id"]
    owned_or_404("notes", note_id, uid)
    db = get_db()
    db.execute("DELETE FROM notes WHERE id=? AND user_id=?", (note_id, uid))
    db.commit()
    flash("Note deleted.", "success")
    return redirect(url_for("notes.index"))
