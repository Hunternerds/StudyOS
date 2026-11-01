from datetime import timedelta

from flask import Blueprint, g, render_template

from ..analytics import service
from ..db import get_db
from ..helpers import MESSAGES, relative_due, user_now, user_today
from ..security import login_required

bp = Blueprint("dashboard", __name__)


def _greeting(hour):
    if hour < 5:
        return "Still up"
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


@bp.route("/")
@login_required
def index():
    db, uid, today = get_db(), g.user["id"], user_today()
    now = user_now()
    week = service.day_series(db, uid, today - timedelta(days=6), today)
    deadlines = [dict(r, due_text=relative_due(r["due_date"], today),
                      overdue=r["due_date"] < today.isoformat())
                 for r in service.upcoming_deadlines(db, uid)]
    return render_template(
        "dashboard/index.html",
        greeting=_greeting(now.hour),
        first_name=g.user["display_name"].split(" ")[0],
        now=now,
        message=MESSAGES[today.toordinal() % len(MESSAGES)],
        stats=service.overview(db, uid),
        streak=service.streak(db, uid, today),
        week=week,
        week_total=sum(d["minutes"] for d in week),
        by_subject=service.time_by_subject(db, uid)[:6],
        sessions=service.recent_sessions(db, uid, 5),
        done_tasks=service.recently_completed(db, uid),
        new_notes=service.recent_notes(db, uid),
        deadlines=deadlines,
    )
