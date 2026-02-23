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

    # Email report settings
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    report_email_to: str = "reshevyas@gmail.com"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
