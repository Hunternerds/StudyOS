"""Authentication guard, CSRF, rate limiting and server-side input validation."""
import hmac
import re
import secrets
import time
from datetime import date
from functools import wraps
from urllib.parse import urlsplit

from flask import abort, current_app, g, redirect, request, session, url_for

from .db import get_db

# ---------------------------------------------------------------- CSRF ----

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def csrf_token():
    token = session.get("_csrf")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf"] = token
    return token


def protect_csrf():
    """before_request hook: every state-changing request needs a valid token."""
    if request.method in SAFE_METHODS or current_app.config.get("CSRF_DISABLED"):
        return None
    expected = session.get("_csrf", "")
    supplied = request.headers.get("X-CSRF-Token") or request.form.get("csrf_token", "")
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(400, description="csrf")
    return None


# ----------------------------------------------------------- auth guard ----

def load_current_user():
    g.user = None
    user_id = session.get("uid")
    if user_id:
        row = get_db().execute(
            "SELECT id, email, display_name, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            session.clear()
        else:
            g.user = row


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.get("user") is None:
            if request.method == "GET":
                return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
            abort(401)
        return view(*args, **kwargs)

    return wrapped


def safe_next(target, fallback):
    """Only allow same-site relative redirects (blocks open redirects)."""
    if not target or not isinstance(target, str):
        return fallback
    if "\\" in target or any(ord(c) < 32 for c in target):
        return fallback
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return fallback
    return target


# --------------------------------------------------------- rate limiting ----

def attempts_in_window(bucket, key, window):
    cutoff = time.time() - window
    row = get_db().execute(
        "SELECT COUNT(*), MIN(created_at) FROM rate_limits "
        "WHERE bucket = ? AND key = ? AND created_at > ?",
        (bucket, key, cutoff),
    ).fetchone()
    return row[0], row[1]


def record_attempt(bucket, key):
    db = get_db()
    db.execute(
        "INSERT INTO rate_limits (bucket, key, created_at) VALUES (?, ?, ?)",
        (bucket, key, time.time()),
    )
    # opportunistic cleanup of rows older than a day
    db.execute("DELETE FROM rate_limits WHERE created_at < ?", (time.time() - 86400,))
    db.commit()


def clear_attempts(bucket, key):
    db = get_db()
    db.execute("DELETE FROM rate_limits WHERE bucket = ? AND key = ?", (bucket, key))
    db.commit()


def retry_after_minutes(oldest, window):
    if oldest is None:
        return 1
    return max(1, int((oldest + window - time.time()) // 60) + 1)


def client_ip():
    return request.remote_addr or "unknown"


# ------------------------------------------------------------ validators ----

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s.]{2,}$")
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
KEY_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

COMMON_PASSWORDS = {
    "password", "password1", "password123", "12345678", "123456789", "1234567890",
    "qwerty123", "qwertyuiop", "iloveyou", "admin123", "letmein123", "welcome123",
    "studyos123", "abc12345", "11111111", "00000000", "passw0rd", "football1",
}


def clean_text(value, max_len, multiline=False):
    """Trim, drop control characters, and cap length. Never returns None."""
    if value is None:
        return ""
    text = _CONTROL.sub("", str(value)).replace("\r\n", "\n").replace("\r", "\n")
    if not multiline:
        text = " ".join(text.split())
    return text.strip()[:max_len]


def valid_email(value):
    return bool(value) and len(value) <= 254 and bool(EMAIL_RE.match(value))


def password_problem(password, email="", name=""):
    if len(password) < 8:
        return "Use at least 8 characters."
    if len(password) > 128:
        return "Password is too long (max 128 characters)."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"[^A-Za-z]", password):
        return "Include letters and at least one number or symbol."
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return "That password is too common."
    if email and lowered == email.lower():
        return "Password can't be your email."
    if name and lowered == name.lower():
        return "Password can't be your name."
    return None


def parse_int(value, low, high, default=None):
    try:
        number = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return number if low <= number <= high else default


def parse_date(value):
    """Return an ISO date string for YYYY-MM-DD input or None."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError:
        return None


def parse_color(value, default="#8b5cf6"):
    value = (value or "").strip()
    return value.lower() if COLOR_RE.match(value) else default


def like_pattern(query):
    """Escape LIKE wildcards so user text is matched literally (use ESCAPE '\\')."""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"
