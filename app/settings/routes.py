from flask import (Blueprint, current_app, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import get_db
from ..helpers import (ACCENTS, AMBIENTS, BG_PRESETS, get_settings, parse_appearance_settings,
                       parse_timer_settings, save_settings)
from ..security import (attempts_in_window, clean_text, clear_attempts, login_required,
                        password_problem, record_attempt, valid_email)

bp = Blueprint("settings", __name__)


def _fetch_request():
    return request.headers.get("X-Requested-With") == "fetch"


@bp.route("/settings")
@login_required
def index():
    return render_template("settings/index.html", s=get_settings(get_db(), g.user["id"]),
                           accents=ACCENTS, presets=BG_PRESETS, ambients=AMBIENTS)


@bp.route("/settings/appearance", methods=["POST"])
@login_required
def save_appearance():
    values, errors = parse_appearance_settings(request.form)
    if errors:
        for message in errors.values():
            flash(message, "error")
    else:
        save_settings(get_db(), g.user["id"], values)
        flash("Appearance saved.", "success")
    return redirect(url_for("settings.index"))


@bp.route("/settings/timer", methods=["POST"])
@login_required
def save_timer():
    source = request.get_json(silent=True) if request.is_json else request.form
    values, errors = parse_timer_settings(source or {})
    if errors:
        if _fetch_request():
            return jsonify({"ok": False, "errors": errors}), 400
        for message in errors.values():
            flash(message, "error")
        return redirect(url_for("settings.index") + "#timer")
    save_settings(get_db(), g.user["id"], values)
    if _fetch_request():
        return jsonify({"ok": True, "settings": get_settings(get_db(), g.user["id"])})
    flash("Timer settings saved.", "success")
    return redirect(url_for("settings.index") + "#timer")


# ---------------------------------------------------------------- profile ----

@bp.route("/profile")
@login_required
def profile():
    db, uid = get_db(), g.user["id"]
    counts = {name: db.execute(f"SELECT COUNT(*) FROM {table} WHERE user_id=?", (uid,)).fetchone()[0]
              for name, table in (("Subjects", "subjects"), ("Assignments", "tasks"), ("Notes", "notes"),
                                  ("Flashcards", "flashcards"), ("Study sessions", "study_sessions"))}
    return render_template("settings/profile.html", counts=counts)


@bp.route("/profile/update", methods=["POST"])
@login_required
def profile_update():
    name = clean_text(request.form.get("name"), 60)
    email = clean_text(request.form.get("email"), 254).lower()
    db, uid = get_db(), g.user["id"]
    if not name or not valid_email(email):
        flash("Enter your name and a valid email address.", "error")
    elif db.execute("SELECT 1 FROM users WHERE email=? AND id<>?", (email, uid)).fetchone():
        flash("That email is already used by another account.", "error")
    else:
        db.execute("UPDATE users SET display_name=?, email=? WHERE id=?", (name, email, uid))
        db.commit()
        flash("Profile updated.", "success")
    return redirect(url_for("settings.profile"))


def _password_ok(db, uid, password):
    bucket = f"pw_{uid}"
    window, limit = current_app.config["LOGIN_WINDOW_SECONDS"], current_app.config["LOGIN_MAX_FAILURES"]
    if attempts_in_window(bucket, "pw", window)[0] >= limit:
        return None  # locked
    row = db.execute("SELECT password_hash FROM users WHERE id=?", (uid,)).fetchone()
    if check_password_hash(row["password_hash"], password):
        clear_attempts(bucket, "pw")
        return True
    record_attempt(bucket, "pw")
    return False


@bp.route("/profile/password", methods=["POST"])
@login_required
def profile_password():
    db, uid = get_db(), g.user["id"]
    current, new, confirm = (request.form.get(k, "") for k in ("current", "new", "confirm"))
    verdict = _password_ok(db, uid, current)
    if verdict is None:
        flash("Too many wrong passwords. Try again later.", "error")
    elif not verdict:
        flash("Your current password is incorrect.", "error")
    else:
        problem = password_problem(new, g.user["email"], g.user["display_name"])
        if problem:
            flash(problem, "error")
        elif new != confirm:
            flash("The new passwords don't match.", "error")
        else:
            db.execute("UPDATE users SET password_hash=? WHERE id=?",
                       (generate_password_hash(new, method=current_app.config["PASSWORD_HASH_METHOD"]), uid))
            db.commit()
            session.clear()  # fresh session after a credential change
            session["uid"] = uid
            session.permanent = True
            flash("Password changed.", "success")
    return redirect(url_for("settings.profile"))


@bp.route("/profile/delete", methods=["POST"])
@login_required
def profile_delete():
    db, uid = get_db(), g.user["id"]
    verdict = _password_ok(db, uid, request.form.get("password", ""))
    if verdict is not True:
        flash("Password incorrect — your account was not deleted." if verdict is False
              else "Too many wrong passwords. Try again later.", "error")
        return redirect(url_for("settings.profile"))
    db.execute("DELETE FROM users WHERE id=?", (uid,))  # cascades to all of this user's data
    db.commit()
    session.clear()
    flash("Your account and all its data were deleted.", "success")
    return redirect(url_for("auth.login"))
