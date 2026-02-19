"""Application configuration."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # Telegram
    telegram_bot_token: str
    telegram_webhook_url: Optional[str] = None
    telegram_webhook_secret: Optional[str] = None
    
    # Database
    database_url: str
    
    # Redis
    redis_url: Optional[str] = None  # Full Redis URL (for Railway)
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    
    # OpenAI
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_premium_model: str = "gpt-4o"
    
    # YooKassa
    yookassa_shop_id: Optional[str] = None
    yookassa_secret_key: Optional[str] = None
    yookassa_return_url: Optional[str] = None
    
    # Admin
    admin_secret_key: Optional[str] = None
    
    # App
    environment: str = "production"
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
