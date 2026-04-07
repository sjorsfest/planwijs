from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+asyncpg://localhost/planwijs"
    database_echo: bool = False
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle: int = 1800
    secret_key: str
    google_client_id: str
    google_client_secret: str
    google_redirect_uri: str 
    oauth_state_secret: str
    openrouter_api_key: str

    cloudflare_r2_account_id: str = ""
    cloudflare_r2_access_key_id: str = ""
    cloudflare_r2_secret_access_key: str = ""
    cloudflare_r2_bucket: str = ""
    cloudflare_r2_public_url: str = ""


settings = Settings()  # type: ignore[call-arg]  # pydantic-settings loads from .env
