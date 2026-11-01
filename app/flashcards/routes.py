from datetime import timedelta

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for

from ..db import get_db
from ..helpers import user_today
from ..ownership import owned_or_404, resolve_subject, user_subjects
from ..security import clean_text, like_pattern, login_required, safe_next

bp = Blueprint("flashcards", __name__)

# Leitner boxes: remembering moves a card up one box; each box waits longer.
# Marking "revise" drops the card to box 1 and keeps it due today.
INTERVAL_DAYS = {1: 1, 2: 3, 3: 7, 4: 14, 5: 30}
MAX_BOX = 5
MAX_STUDY_CARDS = 300


def schedule(box, remembered, today):
    """Pure spaced-repetition step -> (new_box, due_on_iso)."""
    if remembered:
        new_box = min(max(box, 0) + 1, MAX_BOX)
        return new_box, (today + timedelta(days=INTERVAL_DAYS[new_box])).isoformat()
    return 1, today.isoformat()


def _subject_filter(subjects):
    raw = request.args.get("subject", "")
    if raw == "none":
        return "none"
    return int(raw) if raw.isdigit() and int(raw) in {s["id"] for s in subjects} else None


@bp.route("/")
@login_required
def study():
    db, uid, today = get_db(), g.user["id"], user_today()
    iso = today.isoformat()
    subjects = user_subjects(uid)
    subject = _subject_filter(subjects)
    mode = "all" if request.args.get("mode") == "all" else "due"
    where, params = "f.user_id=?", [uid]
    if subject == "none":
        where += " AND f.subject_id IS NULL"
    elif subject is not None:
        where += " AND f.subject_id=?"
        params.append(subject)
    base = ("SELECT f.id, f.question, f.answer, f.box, s.name AS subject, s.color AS color "
            "FROM flashcards f LEFT JOIN subjects s ON s.id=f.subject_id AND s.user_id=f.user_id WHERE ")
    stats = db.execute(
        "SELECT COUNT(*), COALESCE(SUM(due_on IS NULL OR due_on<=?),0), COALESCE(SUM(box>=?),0) "
        "FROM flashcards f WHERE " + where, [iso, MAX_BOX] + params).fetchone()
    if mode == "due":
        sql = base + where + " AND (f.due_on IS NULL OR f.due_on<=?) ORDER BY f.due_on IS NULL, f.due_on, f.id LIMIT ?"
        cards = db.execute(sql, params + [iso, MAX_STUDY_CARDS]).fetchall()
    else:
        cards = db.execute(base + where + " ORDER BY f.id LIMIT ?", params + [MAX_STUDY_CARDS]).fetchall()
    return render_template(
        "flashcards/study.html", cards=[dict(c) for c in cards], subjects=subjects, subject=subject, mode=mode,
        stats={"total": stats[0], "due": stats[1], "mastered": stats[2]})


@bp.route("/manage")
@login_required
def manage():
    db, uid = get_db(), g.user["id"]
    subjects = user_subjects(uid)
    subject = _subject_filter(subjects)
    q = clean_text(request.args.get("q"), 100)
    sql = ("SELECT f.id, f.question, f.answer, f.box, s.name AS subject_name, s.color AS subject_color "
           "FROM flashcards f LEFT JOIN subjects s ON s.id=f.subject_id AND s.user_id=f.user_id WHERE f.user_id=?")
    params = [uid]
    if subject == "none":
        sql += " AND f.subject_id IS NULL"
    elif subject is not None:
        sql += " AND f.subject_id=?"
        params.append(subject)
    if q:
        sql += " AND (f.question LIKE ? ESCAPE '\\' OR f.answer LIKE ? ESCAPE '\\')"
        params += [like_pattern(q)] * 2
    sql += " ORDER BY f.id DESC LIMIT 300"
    return render_template("flashcards/manage.html", cards=db.execute(sql, params).fetchall(),
                           subjects=subjects, subject=subject, q=q)


def _read_form(uid):
    question = clean_text(request.form.get("question"), 1000, multiline=True)
    answer = clean_text(request.form.get("answer"), 2000, multiline=True)
    subject_id, ok = resolve_subject(request.form.get("subject_id"), uid)
    errors = []
    if not question:
        errors.append("Write the question side of the card.")
    if not answer:
        errors.append("Write the answer side of the card.")
    if not ok:
        errors.append("Choose one of your own subjects.")
    return {"question": question, "answer": answer, "subject_id": subject_id}, errors


@bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    uid = g.user["id"]
    form = {"question": "", "answer": "", "subject_id": request.args.get("subject", type=int)}
    if request.method == "POST":
        form, errors = _read_form(uid)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db = get_db()
            db.execute("INSERT INTO flashcards (user_id, subject_id, question, answer, created_at, updated_at) "
                       "VALUES (?,?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
                       (uid, form["subject_id"], form["question"], form["answer"]))
            db.commit()
            flash("Card created.", "success")
            if request.form.get("another"):
                return redirect(url_for("flashcards.create", subject=form["subject_id"] or ""))
            return redirect(url_for("flashcards.manage"))
    return render_template("flashcards/form.html", form=form, card=None, subjects=user_subjects(uid))


@bp.route("/<int:card_id>/edit", methods=["GET", "POST"])
@login_required
def edit(card_id):
    uid = g.user["id"]
    card = owned_or_404("flashcards", card_id, uid)
    form = {"question": card["question"], "answer": card["answer"], "subject_id": card["subject_id"]}
    if request.method == "POST":
        form, errors = _read_form(uid)
        if errors:
            for e in errors:
                flash(e, "error")
        else:
            db = get_db()
            db.execute("UPDATE flashcards SET question=?, answer=?, subject_id=?, updated_at=CURRENT_TIMESTAMP "
                       "WHERE id=? AND user_id=?", (form["question"], form["answer"], form["subject_id"], card_id, uid))
            db.commit()
            flash("Card updated.", "success")
            return redirect(url_for("flashcards.manage"))
    return render_template("flashcards/form.html", form=form, card=card, subjects=user_subjects(uid))


@bp.route("/<int:card_id>/delete", methods=["POST"])
@login_required
def delete(card_id):
    uid = g.user["id"]
    owned_or_404("flashcards", card_id, uid)
    db = get_db()
    db.execute("DELETE FROM flashcards WHERE id=? AND user_id=?", (card_id, uid))
    db.commit()
    flash("Card deleted.", "success")
    return redirect(safe_next(request.form.get("next"), url_for("flashcards.manage")))


@bp.route("/<int:card_id>/review", methods=["POST"])
@login_required
def review(card_id):
    uid, today = g.user["id"], user_today()
    card = owned_or_404("flashcards", card_id, uid)
    result = (request.get_json(silent=True) or {}).get("result")
    if result not in ("remembered", "revise"):
        return jsonify({"ok": False, "error": "Invalid result."}), 400
    remembered = result == "remembered"
    box, due = schedule(card["box"], remembered, today)
    db = get_db()
    db.execute(
        "UPDATE flashcards SET box=?, due_on=?, reviews=reviews+1, lapses=lapses+?, "
        "last_reviewed=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
        (box, due, 0 if remembered else 1, card_id, uid))
    db.commit()
    return jsonify({"ok": True, "box": box, "due_on": due})
