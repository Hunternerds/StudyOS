"""All statistics come from real rows, always filtered by user_id.

Only sessions with kind='focus' count as study time (breaks are never stored).
`subject` filters: None = every subject, "none" = no subject, int = one subject.
"""
from datetime import date, timedelta


def _subject_clause(subject, column="subject_id"):
    if subject is None:
        return "", []
    if subject == "none":
        return f" AND {column} IS NULL", []
    return f" AND {column} = ?", [subject]


# --------------------------------------------------------------- totals ----

def overview(db, uid):
    one = lambda sql: db.execute(sql, (uid,)).fetchone()[0]  # noqa: E731
    minutes = one("SELECT COALESCE(SUM(duration),0) FROM study_sessions "
                  "WHERE user_id=? AND kind='focus'")
    tasks_total = one("SELECT COUNT(*) FROM tasks WHERE user_id=?")
    tasks_done = one("SELECT COUNT(*) FROM tasks WHERE user_id=? AND completed=1")
    return {
        "subjects": one("SELECT COUNT(*) FROM subjects WHERE user_id=?"),
        "tasks_total": tasks_total,
        "tasks_done": tasks_done,
        "tasks_pending": tasks_total - tasks_done,
        "completion_rate": round(tasks_done / tasks_total * 100) if tasks_total else 0,
        "minutes": minutes,
        "hours": round(minutes / 60, 1),
        "sessions": one("SELECT COUNT(*) FROM study_sessions WHERE user_id=? AND kind='focus'"),
        "notes": one("SELECT COUNT(*) FROM notes WHERE user_id=?"),
        "flashcards": one("SELECT COUNT(*) FROM flashcards WHERE user_id=?"),
    }


def streak(db, uid, today):
    """Consecutive study days. Today not yet studied doesn't break the streak."""
    rows = db.execute(
        "SELECT DISTINCT studied_on FROM study_sessions "
        "WHERE user_id=? AND kind='focus' ORDER BY studied_on DESC LIMIT 400", (uid,)
    ).fetchall()
    days = set()
    for row in rows:
        try:
            days.add(date.fromisoformat(row[0]))
        except ValueError:
            continue
    cursor = today if today in days else today - timedelta(days=1)
    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    week = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    return {"current": count, "week": [{"date": d, "studied": d in days} for d in week]}


# ------------------------------------------------------------ time series ----

def daily_minutes(db, uid, start, end, subject=None):
    clause, extra = _subject_clause(subject)
    rows = db.execute(
        "SELECT studied_on, SUM(duration) FROM study_sessions "
        "WHERE user_id=? AND kind='focus' AND studied_on BETWEEN ? AND ?" + clause +
        " GROUP BY studied_on",
        [uid, start.isoformat(), end.isoformat()] + extra,
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def day_series(db, uid, start, end, subject=None):
    data = daily_minutes(db, uid, start, end, subject)
    out, day = [], start
    while day <= end:
        out.append({"label": day.strftime("%a") if (end - start).days < 8 else str(day.day),
                    "sub": day.strftime("%d %b"), "minutes": data.get(day.isoformat(), 0)})
        day += timedelta(days=1)
    return out


def week_start(day):
    return day - timedelta(days=day.weekday())


def week_series(db, uid, today, weeks=8, subject=None, start=None, end=None):
    """Mon-start weekly totals ending with the week that contains `end`/`today`."""
    end = end or today
    last = week_start(end)
    first = start and week_start(start) or last - timedelta(weeks=weeks - 1)
    data = daily_minutes(db, uid, first, end, subject)
    buckets, cursor = [], first
    while cursor <= last:
        total = sum(data.get((cursor + timedelta(days=i)).isoformat(), 0) for i in range(7))
        buckets.append({"label": cursor.strftime("%d %b"),
                        "sub": f"Week of {cursor.strftime('%d %b')}", "minutes": total})
        cursor += timedelta(weeks=1)
    return buckets


def month_series(db, uid, today, months=6, subject=None):
    year, month = today.year, today.month
    spans = []
    for _ in range(months):
        spans.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    spans.reverse()
    first = date(spans[0][0], spans[0][1], 1)
    data = daily_minutes(db, uid, first, today, subject)
    totals = {}
    for iso, minutes in data.items():
        key = (int(iso[:4]), int(iso[5:7]))
        totals[key] = totals.get(key, 0) + minutes
    return [{"label": date(y, m, 1).strftime("%b"),
             "sub": date(y, m, 1).strftime("%B %Y"), "minutes": totals.get((y, m), 0)}
            for y, m in spans]


# --------------------------------------------------------------- by subject ----

def time_by_subject(db, uid, start=None, end=None, subject=None):
    sql = ("SELECT ss.subject_id AS id, COALESCE(s.name,'General study') AS name, "
           "COALESCE(s.color,'#94a3b8') AS color, SUM(ss.duration) AS minutes, "
           "COUNT(*) AS sessions "
           "FROM study_sessions ss "
           "LEFT JOIN subjects s ON s.id = ss.subject_id AND s.user_id = ss.user_id "
           "WHERE ss.user_id=? AND ss.kind='focus'")
    params = [uid]
    if start and end:
        sql += " AND ss.studied_on BETWEEN ? AND ?"
        params += [start.isoformat(), end.isoformat()]
    clause, extra = _subject_clause(subject, "ss.subject_id")
    sql += clause + " GROUP BY ss.subject_id ORDER BY minutes DESC"
    return [dict(r) for r in db.execute(sql, params + extra).fetchall()]


def range_totals(db, uid, start, end, subject=None):
    clause, extra = _subject_clause(subject)
    row = db.execute(
        "SELECT COALESCE(SUM(duration),0), COUNT(*) FROM study_sessions "
        "WHERE user_id=? AND kind='focus' AND studied_on BETWEEN ? AND ?" + clause,
        [uid, start.isoformat(), end.isoformat()] + extra,
    ).fetchone()
    minutes, count = row[0], row[1]
    return {"minutes": minutes, "hours": round(minutes / 60, 1), "sessions": count,
            "average": round(minutes / count) if count else 0}


def recent_sessions(db, uid, limit=8, start=None, end=None, subject=None):
    sql = ("SELECT ss.id, ss.duration, ss.studied_on, ss.created_at, "
           "COALESCE(s.name,'General study') AS subject, COALESCE(s.color,'#94a3b8') AS color "
           "FROM study_sessions ss "
           "LEFT JOIN subjects s ON s.id = ss.subject_id AND s.user_id = ss.user_id "
           "WHERE ss.user_id=? AND ss.kind='focus'")
    params = [uid]
    if start and end:
        sql += " AND ss.studied_on BETWEEN ? AND ?"
        params += [start.isoformat(), end.isoformat()]
    clause, extra = _subject_clause(subject, "ss.subject_id")
    sql += clause + " ORDER BY ss.studied_on DESC, ss.id DESC LIMIT ?"
    return [dict(r) for r in db.execute(sql, params + extra + [limit]).fetchall()]


# ---------------------------------------------------------- dashboard feeds ----

def upcoming_deadlines(db, uid, limit=5):
    return db.execute(
        "SELECT t.id, t.title, t.due_date, t.priority, s.name AS subject, s.color AS color "
        "FROM tasks t LEFT JOIN subjects s ON s.id=t.subject_id AND s.user_id=t.user_id "
        "WHERE t.user_id=? AND t.completed=0 AND t.due_date IS NOT NULL "
        "ORDER BY t.due_date ASC LIMIT ?", (uid, limit)).fetchall()


def recently_completed(db, uid, limit=4):
    return db.execute(
        "SELECT id, title, COALESCE(completed_at, created_at) AS done_at FROM tasks "
        "WHERE user_id=? AND completed=1 ORDER BY done_at DESC LIMIT ?", (uid, limit)).fetchall()


def recent_notes(db, uid, limit=4):
    return db.execute(
        "SELECT id, title, created_at FROM notes WHERE user_id=? "
        "ORDER BY created_at DESC, id DESC LIMIT ?", (uid, limit)).fetchall()
