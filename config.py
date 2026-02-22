from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — app will fail to start without these
    anthropic_api_key: str
    app_api_key: str

    # Optional — Twitter scraper won't work without this
    twitter_bearer_token: str = ""

    # Optional overrides
    claude_model: str = "claude-3-haiku-20240307"
    max_reply_tokens: int = 300

    # Scheduler settings
    scan_hour: int = 17
    scan_minute: int = 0
    scan_timezone: str = "America/New_York"
    scan_max_results: int = 20

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
