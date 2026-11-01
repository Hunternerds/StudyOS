"""StudyOS application factory."""
import os

from flask import Flask, g, jsonify, redirect, render_template, request, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from . import helpers
from .db import close_db, migrate
from .security import csrf_token, load_current_user, protect_csrf

CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src https://fonts.gstatic.com; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "media-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def wants_json():
    return request.headers.get("X-Requested-With") == "fetch" or request.is_json


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object("config.Config")
    if test_config:
        app.config.update(test_config)
    if app.config["TRUSTED_PROXIES"]:
        n = app.config["TRUSTED_PROXIES"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)

    migrate(app.config["DATABASE"])
    app.teardown_appcontext(close_db)
    app.before_request(protect_csrf)
    app.before_request(load_current_user)

    # ---------------------------------------------------------- blueprints --
    from .analytics.routes import bp as analytics_bp
    from .auth.routes import bp as auth_bp
    from .dashboard.routes import bp as dashboard_bp
    from .flashcards.routes import bp as flashcards_bp
    from .notes.routes import bp as notes_bp
    from .settings.routes import bp as settings_bp
    from .subjects.routes import bp as subjects_bp
    from .tasks.routes import bp as tasks_bp
    from .timer.routes import bp as timer_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(subjects_bp, url_prefix="/subjects")
    app.register_blueprint(tasks_bp, url_prefix="/tasks")
    app.register_blueprint(notes_bp, url_prefix="/notes")
    app.register_blueprint(flashcards_bp, url_prefix="/flashcards")
    app.register_blueprint(timer_bp, url_prefix="/timer")
    app.register_blueprint(analytics_bp, url_prefix="/history")
    app.register_blueprint(settings_bp)

    # ------------------------------------------------------------ templating --
    @app.context_processor
    def inject_globals():
        user = g.get("user")
        if user is not None:
            from .db import get_db
            settings = helpers.get_settings(get_db(), user["id"])
        else:
            settings = dict(helpers.DEFAULT_SETTINGS)
        accent = helpers.ACCENTS.get(settings["accent"], helpers.ACCENTS["violet"])[0]
        return {
            "csrf_token": csrf_token,
            "current_user": user,
            "ui": settings,
            "accent_rgb": accent,
            "nav_items": helpers.NAV_ITEMS,
            "ambients": helpers.AMBIENTS,
            "active_section": helpers.active_section(),
            "asset": _asset_url,
            "today": helpers.user_today(),
        }

    def _asset_url(filename):
        """static URL with an mtime cache-buster so edits are picked up."""
        path = os.path.join(app.static_folder, filename)
        version = int(os.path.getmtime(path)) if os.path.exists(path) else 0
        return url_for("static", filename=filename, v=version)

    app.jinja_env.globals["icon"] = helpers.icon
    app.add_template_filter(helpers.local_dt, "localdt")
    app.add_template_filter(helpers.short_date, "shortdate")
    app.add_template_filter(helpers.minutes_label, "minutes")

    # --------------------------------------------------------------- headers --
    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.endpoint != "static":
            response.headers["Cache-Control"] = "no-store"
        return response

    # ---------------------------------------------------------------- errors --
    messages = {
        400: ("Request not accepted", "Your session may have expired or the form was invalid. Reload the page and try again."),
        401: ("Sign in required", "Please sign in to continue."),
        403: ("Not allowed", "You don't have access to that."),
        404: ("Page not found", "That page or item doesn't exist, or it isn't yours."),
        405: ("Method not allowed", "That action isn't available here."),
        413: ("Too much data", "That request was too large."),
        429: ("Slow down", "Too many requests. Please wait a bit and try again."),
        500: ("Something went wrong", "An unexpected error occurred. It has been logged."),
    }

    def render_error(code):
        title, text = messages.get(code, messages[500])
        if code == 401 and not wants_json():
            return redirect(url_for("auth.login"))
        if wants_json():
            return jsonify({"ok": False, "error": text}), code
        return render_template("errors/error.html", code=code, title=title, text=text), code

    for status in messages:
        app.register_error_handler(status, lambda _e, status=status: render_error(status))

    @app.errorhandler(Exception)
    def unexpected(error):
        from werkzeug.exceptions import HTTPException
        if isinstance(error, HTTPException):
            return render_error(error.code or 500)
        app.logger.exception("Unhandled error: %s", error)
        return render_error(500)

    # ------------------------------------------------------------------- cli --
    @app.cli.command("init-db")
    def init_db_command():
        """Create / upgrade the database schema."""
        migrate(app.config["DATABASE"])
        print("Database ready:", app.config["DATABASE"])

    return app
