from datetime import date, timedelta

from flask import Blueprint, g, render_template, request

from ..db import get_db
from ..helpers import user_today
from ..security import login_required, parse_date
from . import service

bp = Blueprint("analytics", __name__)

PRESETS = [("7", "7 days"), ("30", "30 days"), ("90", "90 days"), ("365", "1 year")]


@bp.route("/")
@login_required
def history():
    db, uid, today = get_db(), g.user["id"], user_today()
    subjects = db.execute(
        "SELECT id, name, color FROM subjects WHERE user_id=? ORDER BY name COLLATE NOCASE",
        (uid,)).fetchall()

    # subject filter (ownership verified against the user's own subjects)
    raw_subject = request.args.get("subject", "")
    subject = None
    if raw_subject == "none":
        subject = "none"
    elif raw_subject.isdigit() and int(raw_subject) in {s["id"] for s in subjects}:
        subject = int(raw_subject)

    # date range
    custom_from, custom_to = parse_date(request.args.get("from")), parse_date(request.args.get("to"))
    range_key = request.args.get("range", "30")
    if custom_from and custom_to:
        start, end = date.fromisoformat(custom_from), date.fromisoformat(custom_to)
        range_key = "custom"
    else:
        days = {"7": 7, "30": 30, "90": 90, "365": 365}.get(range_key, 30)
        range_key = range_key if range_key in dict(PRESETS) else "30"
        end, start = today, today - timedelta(days=days - 1)
    end = min(end, today)
    if start > end:
        start = end
    if (end - start).days > 365:
        start = end - timedelta(days=365)

    span = (end - start).days + 1
    if span <= 31:
        main_chart = {"title": "Daily activity", "items": service.day_series(db, uid, start, end, subject)}
    else:
        main_chart = {"title": "Weekly activity in range",
                      "items": service.week_series(db, uid, today, start=start, end=end, subject=subject)}

    return render_template(
        "analytics/history.html",
        subjects=subjects, subject=subject, range_key=range_key, presets=PRESETS,
        start=start, end=end, span=span,
        totals=service.range_totals(db, uid, start, end, subject),
        by_subject=service.time_by_subject(db, uid, start, end, subject),
        main_chart=main_chart,
        weekly=service.week_series(db, uid, today, 8, subject),
        monthly=service.month_series(db, uid, today, 6, subject),
        sessions=service.recent_sessions(db, uid, 15, start, end, subject),
    )
