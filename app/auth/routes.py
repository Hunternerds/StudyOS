from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from ..db import adopt_legacy_rows, get_db
from ..security import (attempts_in_window, clean_text, clear_attempts, client_ip,
                        login_required, password_problem, record_attempt,
                        retry_after_minutes, safe_next, valid_email)

bp = Blueprint("auth", __name__)

# Verified against when the email is unknown so response time doesn't leak
# whether an account exists.
_DUMMY_HASH = generate_password_hash("not-a-real-password", method="pbkdf2:sha256:1000")


def _start_session(user_id):
    session.clear()  # new session on privilege change (prevents fixation)
    session["uid"] = user_id
    session.permanent = True


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("dashboard.index"))
    next_url = safe_next(request.values.get("next"), url_for("dashboard.index"))
    email = ""
    if request.method == "POST":
        email = clean_text(request.form.get("email"), 254).lower()
        password = request.form.get("password", "")[:256]
        cfg = current_app.config
        window, limit = cfg["LOGIN_WINDOW_SECONDS"], cfg["LOGIN_MAX_FAILURES"]
        by_email, oldest = attempts_in_window("login_email", email, window)
        by_ip, oldest_ip = attempts_in_window("login_ip", client_ip(), window)
        if by_email >= limit or by_ip >= limit * 6:
            minutes = retry_after_minutes(oldest if by_email >= limit else oldest_ip, window)
            flash(f"Too many failed attempts. Try again in about {minutes} minute(s).", "error")
            return render_template("auth/login.html", email=email, next_url=next_url), 429

        user = get_db().execute(
            "SELECT id, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
        ok = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password)
        if user and ok:
            clear_attempts("login_email", email)
            db = get_db()
            db.execute(
                "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?", (user["id"],)
            )
            db.commit()
            _start_session(user["id"])
            return redirect(next_url)
        record_attempt("login_email", email)
        record_attempt("login_ip", client_ip())
        flash("Invalid email or password.", "error")
        return render_template("auth/login.html", email=email, next_url=next_url), 401
    return render_template("auth/login.html", email=email, next_url=next_url)


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("dashboard.index"))
    form = {"name": "", "email": ""}
    if request.method == "POST":
        name = clean_text(request.form.get("name"), 60)
        email = clean_text(request.form.get("email"), 254).lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        form = {"name": name, "email": email}

        if attempts_in_window("register_ip", client_ip(), 3600)[0] >= 10:
            flash("Too many sign-ups from this network. Please try again later.", "error")
            return render_template("auth/register.html", form=form), 429

        problems = []
        if not name:
            problems.append("Enter your name.")
        if not valid_email(email):
            problems.append("Enter a valid email address.")
        weak = password_problem(password, email, name)
        if weak:
            problems.append(weak)
        elif password != confirm:
            problems.append("Passwords don't match.")
        db = get_db()
        if not problems and db.execute(
            "SELECT 1 FROM users WHERE email = ?", (email,)
        ).fetchone():
            problems.append("An account with that email already exists.")
        if problems:
            for problem in problems:
                flash(problem, "error")
            return render_template("auth/register.html", form=form), 400

        record_attempt("register_ip", client_ip())
        cursor = db.execute(
            "INSERT INTO users (email, display_name, password_hash) VALUES (?, ?, ?)",
            (email, name, generate_password_hash(
                password, method=current_app.config["PASSWORD_HASH_METHOD"])),
        )
        user_id = cursor.lastrowid
        db.execute("INSERT INTO user_settings (user_id) VALUES (?)", (user_id,))
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1:
            adopt_legacy_rows(db, user_id)  # keep data from before accounts existed
        db.commit()
        _start_session(user_id)
        flash("Welcome to StudyOS.", "success")
        return redirect(url_for("dashboard.index"))
    return render_template("auth/register.html", form=form)


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You've been signed out.", "success")
    return redirect(url_for("auth.login"))
