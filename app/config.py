from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    environment: str = "development"
    debug: bool = False
    allowed_origins: list[str] = ["http://localhost:3000"]

    database_url: str = "postgresql+asyncpg://localhost/planwijs"
    database_echo: bool = False
    database_pool_size: int = 10
    database_max_overflow: int = 20
    database_pool_timeout: int = 30
    database_pool_recycle: int = 1800
    secret_key: str
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str
    oauth_state_secret: str
    openrouter_api_key: str

    redis_url: str = "redis://localhost:6379/0"
    redis_task_ttl_seconds: int = 3600

    cloudflare_r2_account_id: str = ""
    cloudflare_r2_access_key_id: str = ""
    cloudflare_r2_secret_access_key: str = ""
    cloudflare_r2_region: str = "auto"
    cloudflare_r2_public_bucket: str = ""
    cloudflare_r2_public_url: str = ""
    cloudflare_r2_private_bucket: str = "leslab-private"
    signed_url_ttl_seconds: int = 3600


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings loads from .env
    