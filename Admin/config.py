import os
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_files() -> tuple[str, ...]:
    """On Heroku (PORT set), skip .env to avoid any override; use only env vars."""
    if os.environ.get("PORT"):
        return ()  # Heroku: config vars only
    return (".env",)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_files(), env_file_encoding="utf-8", extra="ignore"
    )
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    database_hostname: str = "localhost"
    database_name: str = ""
    database_port: str = "5432"
    database_password: str = ""
    database_username: str = "postgres"
    match_place_id: int = 0  # Roblox place ID for match (set in .env as MATCH_PLACE_ID)
    api_key: str | None = None  # X-API-Key header; if set, all queue endpoints require it
    # roblox_open_cloud_api_key: str
    # roblox_universe_id: str
    # access_token_expire_time: str

    def get_database_url(self) -> str:
        """Return DB URL. Use DATABASE_URL if set (Heroku), else build from individual vars."""
        if self.database_url:
            url = self.database_url
            if url.startswith("postgres://"):
                url = "postgresql://" + url[10:]
            return url
        return (
            f"postgresql://{self.database_username}:{self.database_password}"
            f"@{self.database_hostname}:{self.database_port}/{self.database_name}"
        )


settings = Settings()