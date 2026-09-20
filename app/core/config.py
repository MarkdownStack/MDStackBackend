"""Centralized application settings.

Every environment variable the app reads lives here, in one place — see
backend/SKILL.md's documented gotcha, unchanged by this migration:
Settings is read once per process (get_settings() is lru_cached), so
editing .env while uvicorn is running does nothing until it's restarted.

Postgres migration note: `mongo_url`/`db_name` are gone — nothing in the
app reads them anymore (see app/db/postgres.py/app/db/models.py). This is
plain dead-code removal, not the security fix backend/SKILL.md and the
repo root's SKILL.md describe as still open and owner-only to action: the
real, live MongoDB Atlas password committed to `.env.example` lives in a
separate, already-commented-out block there and is left completely
untouched by this migration (see that file) — nothing here rotates or
removes it.
"""

from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Belt-and-suspenders alongside pydantic-settings' own env_file loading
# below: a few call sites (modules/users/email.py) still read from this
# Settings object rather than os.getenv(...) directly, but load_dotenv()'s
# default `override=False` means it never clobbers a real environment
# variable already set (e.g. Docker's `env_file:` in docker-compose.yml) —
# calling it here, the first of this package's own modules main.py
# imports, guarantees .env is loaded before anything else in the app runs.
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

    # ---- Database ----------------------------------------------------
    # Full SQLAlchemy async URL, e.g.
    # postgresql+asyncpg://user:password@host:5432/dbname — see
    # .env.example. The default matches the local `postgres` service in
    # docker-compose.yml, same "sane local default" spirit the old
    # mongo_url fallback had.
    #
    # In production this points at a managed Postgres instance (e.g. AWS
    # RDS) — a plain, direct connection, same shape as the local default
    # above, just with a different host/user/password/database.
    database_url: str = "postgresql+asyncpg://mdstack:mdstack@localhost:5432/mdstack"

    # ---- Auth / JWT --------------------------------------------------
    jwt_secret_key: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days

    # ---- Admin dashboard ----------------------------------------------
    # Comma-separated list of admin emails, e.g. "you@example.com,x@y.com" —
    # a config change, not a database write. See admin_email_set below.
    admin_emails: str = ""

    # ---- Mailgun (modules/users/email.py) ------------------------------
    mailgun_api_key: str = ""
    # The full "…/v3/<domain>/messages" endpoint, not just a bare domain —
    # this project's Mailgun setup hands out the whole URI directly.
    mailgun_uri: str = ""
    mailgun_from_addr: str = ""
    # Where the frontend is actually served — used to build the
    # /verify-email and /reset-password links embedded in emails (frontend
    # routes, not backend ones).
    frontend_base_url: str = "http://localhost:5173"

    # ---- Logging --------------------------------------------------------
    log_level: str = "INFO"

    @property
    def admin_email_set(self) -> set[str]:
        """Lowercased, stripped, comma-split, empty entries dropped."""
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    @property
    def mailgun_from_email(self) -> str:
        return f"MarkdownStack <{self.mailgun_from_addr}>" if self.mailgun_from_addr else ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
