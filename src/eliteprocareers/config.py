"""
Application configuration, loaded from environment variables / .env file.

Usage:
    from eliteprocareers.config import settings
    print(settings.gemini_api_key)

All config lives here. No other module should call os.getenv() directly —
route new settings through this file so they're validated and typed in one place.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unrelated env vars instead of erroring
    )

    # --- Supabase ---
    # Optional for now (Phase 0) — required once we start Module: DB / Supabase client
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""

    # --- Google Gemini ---
    # Required — the app has no fallback for missing AI credentials
    gemini_api_key: str

    # --- App ---
    app_env: str = "development"
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


# Single shared instance — import this, don't instantiate Settings() elsewhere
settings = Settings()
