from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "dnd_within"
    db_user: str = "dnd"
    db_password: str = "dndpassword"

    # Folders holding content packs, separated by ":". Committed packs live in content/;
    # third-party packs go in content-private/, which is never committed or built into the image.
    content_paths: str = "content:content-private"

    secret_key: str = "change-me"
    session_https_only: bool = False

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


settings = Settings()
