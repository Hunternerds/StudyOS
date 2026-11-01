from flask import Blueprint, g, jsonify, render_template, request

from ..db import get_db
from ..helpers import get_settings, user_today
from ..ownership import resolve_subject, user_subjects
from ..security import KEY_RE, login_required, parse_int

bp = Blueprint("timer", __name__)


@bp.route("/")
@login_required
def index():
    uid = g.user["id"]
    return render_template("timer/index.html", subjects=user_subjects(uid),
                           timer_settings=get_settings(get_db(), uid),
                           preset_subject=request.args.get("subject", type=int))


@bp.route("/complete", methods=["POST"])
@login_required
def complete():
    """Record ONE finished focus session. Idempotent on (user, session_key)."""
    uid, data = g.user["id"], request.get_json(silent=True) or {}
    key = str(data.get("session_key", ""))
    minutes = parse_int(data.get("duration"), 1, 600)
    if not KEY_RE.match(key) or minutes is None:
        return jsonify({"ok": False, "error": "Invalid session."}), 400
    if data.get("kind", "focus") != "focus":  # breaks are never study time
        return jsonify({"ok": False, "error": "Only focus sessions are recorded."}), 400
    raw = data.get("subject_id")
    subject_id, ok = resolve_subject("" if raw in (None, "") else str(raw), uid)
    if not ok:
        return jsonify({"ok": False, "error": "Unknown subject."}), 400

    db = get_db()
    cur = db.execute(
        "INSERT OR IGNORE INTO study_sessions "
        "(user_id, subject_id, duration, studied_on, session_key, started_at, kind, created_at) "
        "VALUES (?,?,?,?,?,?,'focus',CURRENT_TIMESTAMP)",
        (uid, subject_id, minutes, user_today().isoformat(), key, str(data.get("started_at", ""))[:32] or None))
    db.commit()
    total = db.execute(
        "SELECT COALESCE(SUM(duration),0) FROM study_sessions "
        "WHERE user_id=? AND kind='focus' AND studied_on=?", (uid, user_today().isoformat())).fetchone()[0]
    return jsonify({"ok": True, "saved": cur.rowcount == 1, "duplicate": cur.rowcount == 0,
                    "today_minutes": total})
