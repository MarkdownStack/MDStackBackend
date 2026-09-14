"""Centralized application settings.

Every environment variable the app reads used to live as a scattered
``os.getenv(...)`` call at *module import time* across app/auth.py,
app/database.py, app/dependencies.py, and app/email.py — see backend/
SKILL.md's documented gotcha ("editing .env while uvicorn is running does
nothing until restart"). That gotcha is unchanged here (get_settings() is
still cached and still only read once per process, same as before) — what
moves is *where*: one place, so it's no longer a matter of import-order
luck which module happens to trigger python-dotenv's load first.

Every default below is copied **verbatim** from the module it replaces —
including the malformed ``mongo_url`` default — so nothing about runtime
behavior changes just from this file existing.
"""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Belt-and-suspenders alongside pydantic-settings' own env_file loading
# below: a few not-yet-migrated modules (app/email.py, app/dependencies.py
# — see PLAN.md's Phase 2/3) still read os.getenv(...) directly rather than
# going through Settings, exactly like before this restructure. Those still
# need .env's values sitting in the real process environment, which
# pydantic-settings' env_file support does NOT do (it parses the file into
# the Settings object only, it never touches os.environ). This is also the
# first of this package's own modules imported by app/main.py, so calling
# it here — rather than relying on some other module happening to import
# python-dotenv first, which is exactly the fragile accident this
# restructure is fixing — guarantees .env is loaded before anything else in
# the app runs. load_dotenv()'s default `override=False` means it never
# clobbers a real environment variable already set (e.g. Docker's
# `env_file:` in docker-compose.yml), matching prior behavior exactly.
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # .env (see .env.example) also carries MDSTACK_MCP_TOKEN and the
        # mcp_server-only MDSTACK_* vars — this app has no field for those,
        # and pydantic-settings hard-fails on unrecognized keys without this.
        extra="ignore",
        case_sensitive=False,
    )

    # ---- Database (was app/database.py) ---------------------------------
    mongo_url: str = "http:localhost:27017/"
    db_name: str = "test_db"

    # ---- Auth / JWT (was app/auth.py) ------------------------------------
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # ---- Admin dashboard (was app/dependencies.py) -----------------------
    # Comma-separated list of admin emails, e.g. "you@example.com,x@y.com" —
    # a config change, not a database write. See admin_email_set below.
    admin_emails: str = ""

    # ---- Mailgun (was app/email.py) --------------------------------------
    mailgun_api_key: str = ""
    # The full "…/v3/<domain>/messages" endpoint, not just a bare domain —
    # this project's Mailgun setup hands out the whole URI directly.
    mailgun_uri: str = ""
    mailgun_from_addr: str = ""
    # Where the frontend is actually served — used to build the
    # /verify-email and /reset-password links embedded in emails (frontend
    # routes, not backend ones).
    frontend_base_url: str = "http://localhost:5173"

    # ---- Logging (new — see core/logging.py) ------------------------------
    log_level: str = "INFO"

    @property
    def admin_email_set(self) -> set[str]:
        """Same parsing app/dependencies.py did once at import time:
        lowercased, stripped, comma-split, empty entries dropped."""
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def mailgun_from_email(self) -> str:
        return f"MarkdownStack <{self.mailgun_from_addr}>" if self.mailgun_from_addr else ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
