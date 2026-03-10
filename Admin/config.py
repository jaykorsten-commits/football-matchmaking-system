from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str | None = None  # Heroku sets DATABASE_URL
    database_hostname: str = "localhost"
    database_name: str = ""
    database_port: str = "5432"
    database_password: str = ""
    database_username: str = "postgres"
    match_place_id: int = 0  # Roblox place ID for match (set in .env as MATCH_PLACE_ID)
    # roblox_open_cloud_api_key: str
    # roblox_universe_id: str
    # access_token_expire_time: str

    class Config:
        env_file = ".env"

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