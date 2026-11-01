"""Cross-cutting helpers: per-user settings, local time, formatting, nav model."""
from datetime import date, datetime, timedelta, timezone

from flask import request

from .security import clean_text, parse_int

# ------------------------------------------------------------- constants ----

ACCENTS = {
    "violet": ("139 92 246", "Violet"),
    "indigo": ("99 102 241", "Indigo"),
    "cyan": ("34 211 238", "Cyan"),
    "emerald": ("52 211 153", "Emerald"),
    "rose": ("244 114 182", "Rose"),
    "amber": ("251 191 36", "Amber"),
}

BG_PRESETS = [
    ("cosmic-night", "Cosmic Night"),
    ("purple-nebula", "Purple Nebula"),
    ("enchanted-forest", "Enchanted Forest"),
    ("midnight-ocean", "Midnight Ocean"),
    ("minimal-dark", "Minimal Dark"),
    ("animated-stars", "Animated Stars"),
]

AMBIENTS = [("off", "Off"), ("brown", "Brown noise"), ("rain", "Rain"), ("white", "White noise")]

DEFAULT_SETTINGS = {
    "focus_min": 25, "short_min": 5, "long_min": 15, "sessions_before_long": 4,
    "auto_start_breaks": 0, "auto_start_focus": 0, "sound_enabled": 1,
    "ambient": "off", "ambient_volume": 35,
    "bg_preset": "cosmic-night", "bg_animated": 1, "bg_intensity": 70,
    "reduce_motion": 0, "accent": "violet",
}

# (section key, endpoint, label, icon)
NAV_ITEMS = [
    ("dashboard", "dashboard.index", "Dashboard", "dashboard"),
    ("subjects", "subjects.index", "Subjects", "subjects"),
    ("tasks", "tasks.index", "Tasks & Assignments", "tasks"),
    ("notes", "notes.index", "Notes", "notes"),
    ("flashcards", "flashcards.study", "Flashcards", "cards"),
    ("analytics", "analytics.history", "Study History", "history"),
    ("settings", "settings.index", "Settings", "settings"),
    ("profile", "settings.profile", "Profile", "user"),
]

MESSAGES = [
    "Small, steady sessions beat last-minute marathons.",
    "Start with the hardest topic while your mind is fresh.",
    "One focused block today is progress you can build on.",
    "Review a little every day and it will stick.",
    "Plan the next step, then take it.",
    "Rest is part of studying. Protect your breaks.",
    "Consistency matters more than intensity.",
]


def active_section():
    """Derived from the real Flask route, never hardcoded in templates."""
    endpoint = request.endpoint or ""
    if endpoint.startswith("settings.profile"):
        return "profile"
    return request.blueprint or ""


# ------------------------------------------------------------- local time ----

def tz_offset_minutes():
    """Browser offset (minutes behind UTC) from the `tzoff` cookie set by app.js."""
    try:
        value = int(request.cookies.get("tzoff", "0"))
    except ValueError:
        return 0
    return value if -840 <= value <= 840 else 0


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def user_now():
    return utc_now() - timedelta(minutes=tz_offset_minutes())


def user_today():
    return user_now().date()


def _parse_ts(value):
    if not value:
        return None
    text = str(value).replace("T", " ").split(".")[0].replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def local_dt(value, fmt="%d %b %Y, %H:%M"):
    moment = _parse_ts(value)
    if moment is None:
        return ""
    if len(str(value)) > 10:  # timestamps are stored in UTC; plain dates are not
        moment -= timedelta(minutes=tz_offset_minutes())
    return moment.strftime(fmt)


def short_date(value):
    if not value:
        return ""
    try:
        parsed = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    except ValueError:
        return ""
    return f"{parsed.day} {parsed.strftime('%b')}"


def minutes_label(total):
    total = int(total or 0)
    hours, minutes = divmod(total, 60)
    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"


def relative_due(due_iso, today):
    """Human text for a deadline relative to `today` (a date)."""
    if not due_iso:
        return ""
    try:
        due = date.fromisoformat(due_iso)
    except ValueError:
        return ""
    delta = (due - today).days
    if delta == 0:
        return "Due today"
    if delta == 1:
        return "Due tomorrow"
    if delta == -1:
        return "1 day overdue"
    if delta < 0:
        return f"{-delta} days overdue"
    if delta < 7:
        return f"Due in {delta} days"
    return f"Due {short_date(due)}"


# --------------------------------------------------------------- settings ----

def get_settings(db, user_id):
    row = db.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
        db.commit()
        row = db.execute("SELECT * FROM user_settings WHERE user_id = ?", (user_id,)).fetchone()
    return dict(row)


def _flag(source, name):
    return 1 if str(source.get(name, "")).lower() in {"1", "true", "on", "yes"} else 0


def parse_timer_settings(source):
    """Validate timer settings from a form or JSON dict -> (values, errors)."""
    errors = {}
    values = {}
    ranges = {
        "focus_min": (1, 180, "Focus"), "short_min": (1, 60, "Short break"),
        "long_min": (1, 120, "Long break"), "sessions_before_long": (1, 12, "Sessions before long break"),
    }
    for name, (low, high, label) in ranges.items():
        number = parse_int(source.get(name), low, high)
        if number is None:
            errors[name] = f"{label} must be between {low} and {high}."
        values[name] = number
    values["auto_start_breaks"] = _flag(source, "auto_start_breaks")
    values["auto_start_focus"] = _flag(source, "auto_start_focus")
    values["sound_enabled"] = _flag(source, "sound_enabled")
    ambient = clean_text(source.get("ambient", "off"), 12)
    if ambient not in dict(AMBIENTS):
        errors["ambient"] = "Unknown ambient sound."
    values["ambient"] = ambient
    volume = parse_int(source.get("ambient_volume", 35), 0, 100)
    if volume is None:
        errors["ambient_volume"] = "Volume must be between 0 and 100."
    values["ambient_volume"] = volume
    return values, errors


def parse_appearance_settings(source):
    errors = {}
    preset = clean_text(source.get("bg_preset"), 32)
    if preset not in dict(BG_PRESETS):
        errors["bg_preset"] = "Choose one of the listed backgrounds."
    intensity = parse_int(source.get("bg_intensity"), 20, 100)
    if intensity is None:
        errors["bg_intensity"] = "Intensity must be between 20 and 100."
    accent = clean_text(source.get("accent"), 16)
    if accent not in ACCENTS:
        errors["accent"] = "Choose one of the listed accent colors."
    return {
        "bg_preset": preset, "bg_animated": _flag(source, "bg_animated"),
        "bg_intensity": intensity, "reduce_motion": _flag(source, "reduce_motion"),
        "accent": accent,
    }, errors


def save_settings(db, user_id, values):
    # column names come from our own validated dict keys, never from user input
    allowed = set(DEFAULT_SETTINGS)
    items = [(k, v) for k, v in values.items() if k in allowed]
    db.execute("INSERT OR IGNORE INTO user_settings (user_id) VALUES (?)", (user_id,))
    assignments = ", ".join(f"{key} = ?" for key, _ in items)
    db.execute(
        f"UPDATE user_settings SET {assignments} WHERE user_id = ?",
        [value for _, value in items] + [user_id],
    )
    db.commit()


# ------------------------------------------------------------------ icons ----

ICON_NAMES = {
    "menu", "close", "dashboard", "timer", "subjects", "tasks", "notes", "cards", "history",
    "settings", "user", "logout", "plus", "edit", "trash", "search", "check", "play", "pause",
    "reset", "skip", "fullscreen", "exit-fullscreen", "flame", "calendar", "flag", "alert",
    "chevron-left", "chevron-right", "shuffle", "flip", "volume", "volume-off", "lock", "mail",
    "clock", "spark", "arrow-right", "target", "list",
}


def icon(name, css_class=""):
    """Render one icon from the shared sprite (templates/partials/icons.html)."""
    from markupsafe import Markup, escape
    if name not in ICON_NAMES:
        raise ValueError(f"unknown icon: {name}")
    extra = f" {escape(css_class)}" if css_class else ""
    return Markup(
        f'<svg class="icon{extra}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">'
        f'<use href="#i-{name}"/></svg>'
    )
