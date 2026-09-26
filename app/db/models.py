"""SQLAlchemy ORM models — the Postgres schema, replacing the Mongo
collections documented in the old backend/SKILL.md's "Data model" section.

Relationships, at a glance:

    User 1---1 UserPreferences   (one settings row per account)
    User 1---* Folder            (a folder always belongs to exactly one user)
    User 1---* Note              (a note always belongs to exactly one user)
    Folder 1---* Note            (nullable: see Note.folder_id below)
    Note *---* Tag               (through note_tags)
    Note 1---* Comment
    User 1---* Comment           (the commenter's real account — no
                                   anonymous/free-typed authors)
    User 1---* SlugRedirect      (owner-scoped custom short URLs for
                                   published notes and folders)

Primary keys are UUIDs (`uuid4`, stored as native Postgres UUID) rather
than auto-increment integers, deliberately: the old Mongo `ObjectId`
strings were already opaque ids as far as the frontend/API contract is
concerned (`NoteOut.id: str`, etc.), so UUIDs keep that contract identical
— nothing calling this API needs to change just because the id format
changed from a 24-hex-char ObjectId to a 36-char UUID string.

All free-text content (`Note.content`, `Comment.content`) is `Text`, not
`String(n)` — unbounded, same as Mongo's schemaless string fields, per the
migration brief's "use text data type for storing md file content".
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Column,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import Computed

from .postgres import Base


def _new_uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# users
# ---------------------------------------------------------------------------


class User(Base):
    """One row per account. Admin status is still computed at read time
    from Settings.admin_email_set (see shared/dependencies.py) rather than
    stored here — same "config, not a database write" design the Mongo
    version had."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    # Nullable + unique (not sparse-unique the way Mongo needed to spell it):
    # a plain Postgres UNIQUE constraint already allows any number of NULLs
    # through without them colliding with each other, which is exactly the
    # "old accounts predating the username field have none" case the Mongo
    # sparse index existed for.
    username: Mapped[str | None] = mapped_column(String(24), nullable=True, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    verification_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_reset_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    password_reset_token_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Subscription flag — false for every new account, flipped to true
    # when the user obtains a Pro plan. Gates the AI chat feature on the
    # frontend (see AIChatDialog / VaultShell). The billing/payment flow
    # that sets this to true is a future feature; for now it can only be
    # toggled manually (e.g. via the admin dashboard or a direct DB update).
    is_subscribed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # No `onupdate=func.now()` here deliberately: with an async session, a
    # server-computed onupdate value comes back "expired" after an UPDATE
    # and needs an extra round trip (session.refresh()) before it can be
    # read back — easy to get wrong under asyncio (SQLAlchemy's
    # MissingGreenlet trap: a lazy re-fetch triggered from plain,
    # un-awaited attribute access). Every write path that should bump this
    # timestamp sets it explicitly instead (a plain Python
    # `datetime.now(timezone.utc)` assignment — no SQL expression, so
    # nothing is ever "expired"), the same app-managed timestamp control
    # the old Mongo code always had (`updated_at: now_iso()` on every
    # `$set`). Every other table below with an `updated_at` follows this
    # same pattern, for the same reason.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    preferences: Mapped["UserPreferences | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    folders: Mapped[list["Folder"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    notes: Mapped[list["Note"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    tags: Mapped[list["Tag"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    comments: Mapped[list["Comment"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    slugs: Mapped[list["SlugRedirect"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class UserPreferences(Base):
    """Per-account settings — dark mode, autosave interval, reading font,
    etc. New table: these lived only in the frontend's localStorage before
    this migration (see ThemeContext/SettingsContext/ReadingFontContext),
    which is why every column below has a default matching that frontend's
    existing default exactly. One-to-one with User via a shared primary
    key (`user_id` is both the PK and the FK) — the standard SQLAlchemy/
    Postgres pattern for "exactly one of these per parent row, created
    lazily on first read" (see modules/preferences/service.py)."""

    __tablename__ = "user_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    theme: Mapped[str] = mapped_column(String(10), nullable=False, default="dark")
    autosave_interval_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=300_000)
    spotlight_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    live_preview_editing_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    justify_text_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reading_font_id: Mapped[str] = mapped_column(String(32), nullable=False, default="inter")
    reading_font_size_id: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    # Catch-all for anything that doesn't deserve its own column yet (e.g. a
    # future per-account keyboard shortcut override map — see frontend's
    # ShortcutsContext) — a JSONB blob beats a schema migration for every
    # small new preference someone adds.
    extra: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # No `onupdate=func.now()` here deliberately — see User.updated_at's
    # comment above: every write path that should bump this timestamp sets
    # it explicitly in Python instead, to avoid async SQLAlchemy's
    # expired-attribute/MissingGreenlet trap on a server-computed value.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="preferences")


# ---------------------------------------------------------------------------
# folders
# ---------------------------------------------------------------------------


class Folder(Base):
    """Scoped by owner. `created_at`/`updated_at` are nullable — preserved
    quirk from the Mongo version: a folder created implicitly by upload's
    ensure_folder_chain (an auto-created ancestor of an uploaded file's
    path) never got timestamps, unlike one created via POST /api/folders
    or the publish-upsert, which always stamp both (see modules/folders and
    modules/upload's repository.py docstrings)."""

    __tablename__ = "folders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(Text, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="folders")
    # A note's folder_id is nullable (see Note below) — a folder can have
    # zero, one, or many notes, so this is a plain one-to-many, not
    # something a delete on Folder should cascade through (folder delete
    # is handled explicitly, path-scoped, in modules/folders/service.py's
    # cascade delete — a stray FK-level cascade here would delete the
    # wrong set of notes for a folder that has descendants of its own).
    notes: Mapped[list["Note"]] = relationship(back_populates="folder")

    __table_args__ = (
        UniqueConstraint("owner_id", "path", name="uq_folders_owner_path"),
        Index("ix_folders_owner_public", "owner_id", "is_public"),
    )


# ---------------------------------------------------------------------------
# notes + tags (many-to-many)
# ---------------------------------------------------------------------------

# Plain association table (no extra columns needed) — a note either has a
# tag or it doesn't; unlike Mongo's tags array, there's no per-row "order
# tag was first typed" data worth preserving here (see
# shared/markdown.extract_tags — insertion order mattered there only
# because a Python list is what came back; the API's `tags: List[str]`
# reads the same to a caller whether it's alphabetized or insertion-order).
# modules/notes/repository.py orders it alphabetically on read for a
# deterministic, index-friendly result instead.
note_tags = Table(
    "note_tags",
    Base.metadata,
    Column("note_id", UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class Tag(Base):
    """A #tag, scoped per-owner (the same tag text used by two different
    accounts is two different rows — tags are private-vault metadata, not
    a shared/global taxonomy). Normalized out of Mongo's plain `tags: []`
    array on the note document into a real many-to-many relationship, per
    this migration's brief to make entity relationships explicit."""

    __tablename__ = "tags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    owner: Mapped["User"] = relationship(back_populates="tags")
    notes: Mapped[list["Note"]] = relationship(secondary=note_tags, back_populates="tags")

    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_tags_owner_name"),
        Index("ix_tags_owner_name", "owner_id", "name"),
    )


class Note(Base):
    """Scoped by owner; `title` unique per owner (mirrors the Mongo unique
    index). `content` is `Text` — unbounded markdown source, per the
    migration brief.

    `folder_id` is a *nullable* FK rather than a required one: Mongo's
    notes were scoped by a free-text `folder_path` that didn't always have
    a backing `folders` document (an "implied" folder — see
    modules/folders/service.py's list_folders docstring). `folder_path`
    is kept as its own column (not derived from a join) for exactly that
    reason — a note can have a folder_path with no matching Folder row at
    all, same as before. Whenever a real Folder row *does* exist at that
    path, `folder_id` points at it (kept in sync in modules/notes/service.py
    and modules/upload/service.py); code that needs "every note under this
    folder's subtree" still scopes by `folder_path` via
    shared/paths.folder_scope_clause() rather than the FK, since an implied
    subfolder several levels down may have no Folder row of its own either.

    `search_vector` is a stored generated column (computed by Postgres
    itself on every insert/update, not by the application) backing full-
    text search — see modules/notes/repository.py's text_search(), which
    replaces Mongo's `$text` index. `to_tsvector('english', ...)` is not a
    regular expression; it's Postgres's own text-search tokenizer/
    stemmer, unrelated to the regex the previous `shared/markdown.py`
    used for tag/link extraction (deliberately not carried over — see that
    file's new docstring)."""

    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="SET NULL"), nullable=True
    )
    folder_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Wikilink targets (titles this note links to) — kept as a plain text
    # array, same shape Mongo stored, since backlink lookups are a single
    # "does this note's links array contain my title" query either way
    # (col.any_(title) -> `title = ANY(notes.links)` in Postgres — array
    # containment, not a regex match).
    links: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    upvotes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    downvotes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # No `onupdate=func.now()` here deliberately — see User.updated_at's
    # comment above: every write path that should bump this timestamp sets
    # it explicitly in Python instead, to avoid async SQLAlchemy's
    # expired-attribute/MissingGreenlet trap on a server-computed value.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('english', coalesce(title, '') || ' ' || coalesce(content, ''))", persisted=True),
        nullable=True,
    )

    owner: Mapped["User"] = relationship(back_populates="notes")
    folder: Mapped["Folder | None"] = relationship(back_populates="notes")
    tags: Mapped[list["Tag"]] = relationship(secondary=note_tags, back_populates="notes")
    comments: Mapped[list["Comment"]] = relationship(back_populates="note", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("owner_id", "title", name="uq_notes_owner_title"),
        Index("ix_notes_owner_folder_path", "owner_id", "folder_path"),
        Index("ix_notes_public_upvotes", "is_public", "upvotes"),
        Index("ix_notes_links_gin", "links", postgresql_using="gin"),
        Index("ix_notes_search_vector_gin", "search_vector", postgresql_using="gin"),
    )


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------


class Comment(Base):
    """Author is always a real account (`owner_id`) — no free-typed names,
    matching the Mongo version's "no anonymous spoofing" rule."""

    __tablename__ = "comments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    note_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("notes.id", ondelete="CASCADE"), nullable=False
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    upvotes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # No `onupdate=func.now()` here deliberately — see User.updated_at's
    # comment above: every write path that should bump this timestamp sets
    # it explicitly in Python instead, to avoid async SQLAlchemy's
    # expired-attribute/MissingGreenlet trap on a server-computed value.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    note: Mapped["Note"] = relationship(back_populates="comments")
    owner: Mapped["User"] = relationship(back_populates="comments")

    __table_args__ = (
        Index("ix_comments_note_created", "note_id", "created_at"),
        Index("ix_comments_note_upvotes", "note_id", "upvotes"),
    )


# ---------------------------------------------------------------------------
# request_stats — admin dashboard traffic counter
# ---------------------------------------------------------------------------


class RequestStat(Base):
    """One row per UTC calendar day — same shape as the Mongo version
    (`_id` was literally the "YYYY-MM-DD" string; here that's the primary
    key column instead). Written only by core/middleware.py's
    RequestCounterMiddleware, read only by modules/admin. Not owned by any
    user — this is vault-wide traffic, not per-account data, so it has no
    FK to `users`."""

    __tablename__ = "request_stats"

    date: Mapped[str] = mapped_column(String(10), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Per-HTTP-method breakdown ({"GET": 41, "POST": 3, ...}) — was
    # dot-path fields (`methods.GET`) inside the same Mongo doc; a JSONB
    # column is the direct Postgres equivalent of "a small nested object
    # that isn't worth its own table".
    methods: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


# ---------------------------------------------------------------------------
# slug_redirects — custom short URLs for published notes and folders
# ---------------------------------------------------------------------------


class SlugRedirect(Base):
    """A user-chosen short slug (e.g. "python-oop-concepts") that resolves
    to either a published note or a published folder. Slugs are globally
    unique across all users — two accounts cannot claim the same slug, and
    the resolution endpoint is unauthenticated (it has to be, since it's a
    public URL). Owner-scoped in the sense that only the note/folder owner
    can set or change the slug for their own content; the global uniqueness
    constraint is what prevents squatting on another user's slug.

    `target_type` is either "note" or "folder" — kept as a plain string
    rather than a Postgres enum so adding a third type later (e.g. a tag
    page) is a code change only, not a schema migration.

    A note or folder can have at most one active slug (enforced by the
    unique constraint on (target_type, target_id)). Changing the slug
    replaces the row in-place (upsert in service.py); the old slug is
    immediately gone, not kept as a redirect, so links using the previous
    slug 404. This is intentional: we're not a link-management SaaS, just
    a vanity-URL picker that makes sharing nicer.
    """

    __tablename__ = "slug_redirects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_new_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # URL-safe slug: lowercase letters, digits, hyphens only, 3–80 chars.
    # Validated in schemas.py; stored as-is (already lowercased by the
    # validator so lookups are a plain equality check, not LOWER()).
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    # "note" | "folder"
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    # The UUID of the note or folder this slug points at. Not a real FK
    # because it could point to either the `notes` or `folders` table —
    # enforced at the service layer (the target must be published and
    # belong to the owner) rather than at the DB level.
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    owner: Mapped["User"] = relationship(back_populates="slugs")

    __table_args__ = (
        # One slug per (type, target) — a note can't have two slugs at once.
        UniqueConstraint("target_type", "target_id", name="uq_slug_target"),
        Index("ix_slug_redirects_slug", "slug"),
        Index("ix_slug_redirects_owner", "owner_id"),
    )
