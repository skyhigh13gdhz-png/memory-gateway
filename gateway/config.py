from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8787
    gateway_api_token: str
    hindsight_base_url: str = "http://127.0.0.1:8888"
    default_bank_id: str = "default"
    hindsight_timeout_seconds: float = 120.0


settings = Settings()
