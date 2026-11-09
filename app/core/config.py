from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET_KEY = "change-me"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_name: str = "dnd_within"
    db_user: str = "dnd"
    db_password: str = "dndpassword"

    content_paths: str = "content-private"

    secret_key: str = DEV_SECRET_KEY
    session_https_only: bool = False

    @model_validator(mode="after")
    def check_secret_key(self):
        if not self.secret_key:
            raise ValueError("SECRET_KEY is empty")
        if self.session_https_only and (
            self.secret_key == DEV_SECRET_KEY or len(self.secret_key) < MIN_SECRET_KEY_LENGTH
        ):
            raise ValueError(
                f"SECRET_KEY must be a random value of at least {MIN_SECRET_KEY_LENGTH} "
                "characters when SESSION_HTTPS_ONLY is on. Generate one with: "
                'python3 -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
        return self

    @property
    def database_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


settings = Settings()
