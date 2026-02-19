"""Application configuration."""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings."""
    
    # Telegram (REQUIRED)
    telegram_bot_token: str
    
    # Telegram webhook (optional - not used in polling mode)
    telegram_webhook_url: Optional[str] = None
    telegram_webhook_secret: Optional[str] = None
    
    # Database (REQUIRED)
    database_url: str
    
    # Redis (optional - will use memory fallback if not available)
    redis_url: Optional[str] = None  # Full Redis URL (for Railway)
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    
    # OpenAI (optional - required for analysis features)
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_premium_model: str = "gpt-4o"
    
    # YooKassa (optional - required for payments)
    yookassa_shop_id: Optional[str] = None
    yookassa_secret_key: Optional[str] = None
    yookassa_return_url: Optional[str] = None
    
    # Admin (optional)
    admin_secret_key: Optional[str] = None
    
    # App
    environment: str = "production"
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
