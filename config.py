from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # API Keys
    anthropic_api_key: str = ""
    twitter_bearer_token: str = ""
    app_api_key: str = ""

    # Optional overrides
    claude_model: str = "claude-sonnet-4-5-20250514"
    max_reply_tokens: int = 300

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
