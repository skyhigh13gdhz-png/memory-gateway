from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # 生产运行时由 systemd EnvironmentFile 注入配置。
    # 不在应用进程中再次读取 .env，避免服务用户与 root-owned 0600 文件发生权限冲突。
    model_config = SettingsConfigDict(extra="ignore")

    gateway_host: str = "127.0.0.1"
    gateway_port: int = 8787
    gateway_api_token: str
    hindsight_base_url: str = "http://127.0.0.1:8888"
    default_bank_id: str = "default"
    hindsight_timeout_seconds: float = 120.0


settings = Settings()
