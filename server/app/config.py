from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "TradePilot"
    secret_key: str = ""
    access_token_minutes: int = 60
    database_path: str = "./tradepilot.db"
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    demo_only: bool = True
    pairing_ttl_seconds: int = 300
    max_commands_per_minute: int = 60
    command_result_timeout_seconds: int = 30
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
