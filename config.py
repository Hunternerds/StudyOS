"""StudyOS configuration. Secrets come from environment variables / .env."""
import os
import secrets
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"


def load_env_file(path):
    """Tiny .env loader (no python-dotenv dependency, works on Android Python)."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env_file(BASE_DIR / ".env")


def _env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _secret_key(is_production):
    key = os.environ.get("SECRET_KEY")
    if key:
        return key
    if is_production:
        raise RuntimeError("SECRET_KEY must be set when STUDYOS_ENV=production.")
    # Development: generate once and persist so sessions survive restarts.
    INSTANCE_DIR.mkdir(parents=True, exist_ok=True)
    key_file = INSTANCE_DIR / "dev_secret_key"
    if not key_file.exists():
        key_file.write_text(secrets.token_hex(32))
        try:
            key_file.chmod(0o600)
        except OSError:
            pass
    return key_file.read_text().strip()


def _default_database():
    explicit = os.environ.get("DATABASE_PATH")
    if explicit:
        return explicit
    legacy = BASE_DIR / "data" / "studyos.db"
    # Keep using the pre-accounts database if it exists so no data is lost.
    if legacy.is_file():
        return str(legacy)
    return str(INSTANCE_DIR / "studyos.db")


class Config:
    ENVIRONMENT = os.environ.get("STUDYOS_ENV", "development").lower()
    IS_PRODUCTION = ENVIRONMENT == "production"
    SECRET_KEY = _secret_key(IS_PRODUCTION)
    DATABASE = _default_database()

    SESSION_COOKIE_NAME = "studyos_session"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", IS_PRODUCTION)
    PERMANENT_SESSION_LIFETIME = timedelta(
        days=int(os.environ.get("SESSION_LIFETIME_DAYS", "7"))
    )
    MAX_CONTENT_LENGTH = 512 * 1024  # request bodies are small text only

    # pbkdf2 works on every Python build (scrypt can be missing on Android).
    PASSWORD_HASH_METHOD = os.environ.get("PASSWORD_HASH_METHOD", "pbkdf2:sha256:600000")

    LOGIN_MAX_FAILURES = int(os.environ.get("LOGIN_MAX_FAILURES", "5"))
    LOGIN_WINDOW_SECONDS = int(os.environ.get("LOGIN_WINDOW_SECONDS", "900"))
    TRUSTED_PROXIES = int(os.environ.get("TRUSTED_PROXIES", "0"))
    TESTING = False
