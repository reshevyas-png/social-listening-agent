from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Required — app will fail to start without these
    anthropic_api_key: str = ""
    app_api_key: str

    # OpenRouter (primary) — falls back to Anthropic if not set
    openrouter_api_key: str = ""
    llm_provider: str = "auto"  # "openrouter", "anthropic", or "auto"

    # Twitter — bearer for reading, OAuth for posting
    twitter_bearer_token: str = ""
    twitter_api_key: str = ""
    twitter_api_secret: str = ""
    twitter_access_token: str = ""
    twitter_access_secret: str = ""
    auto_post_replies: bool = False  # requires manual approval via dashboard

    # GitHub — for stargazer lead sync
    github_token: str = ""

    # Optional overrides
    claude_model: str = "claude-sonnet-4-20250514"
    max_reply_tokens: int = 300

    # Scheduler settings
    scan_hour: int = 17
    scan_minute: int = 0
    scan_timezone: str = "America/New_York"
    scan_max_results: int = 20
    scan_max_replies: int = 15  # cap replies per scan (top engagement first)

    # Email report settings
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    report_email_to: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
