"""Request/response models for /api/preferences — new module, backing the
per-account settings this migration's brief calls for (dark mode, etc.).

Every default here matches the frontend's existing localStorage defaults
exactly (see ThemeContext/SettingsContext/ReadingFontContext) — this
endpoint is additive, a place for those settings to live server-side and
follow the account across devices, not a replacement the frontend has to
adopt in this pass to keep working."""

from typing import Optional

from pydantic import BaseModel, Field


class PreferencesOut(BaseModel):
    theme: str = "dark"
    autosave_interval_ms: int = 300_000
    spotlight_enabled: bool = True
    live_preview_editing_enabled: bool = True
    justify_text_enabled: bool = True
    reading_font_id: str = "inter"
    reading_font_size_id: str = "medium"
    extra: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str


class PreferencesUpdate(BaseModel):
    """Every field optional — same partial-update shape as NoteUpdate:
    only the fields the caller actually sends are changed."""

    theme: Optional[str] = None
    autosave_interval_ms: Optional[int] = Field(default=None, ge=1_000)
    spotlight_enabled: Optional[bool] = None
    live_preview_editing_enabled: Optional[bool] = None
    justify_text_enabled: Optional[bool] = None
    reading_font_id: Optional[str] = None
    reading_font_size_id: Optional[str] = None
    extra: Optional[dict] = None
