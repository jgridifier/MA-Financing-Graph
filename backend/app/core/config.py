"""
Application configuration with fail-fast validation.
SEC User-Agent compliance is mandatory.
"""
import re
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "MAFinancingApp"
    ADMIN_EMAIL: str
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/ma_financing"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # SEC EDGAR
    SEC_BASE_URL: str = "https://www.sec.gov"
    SEC_RATE_LIMIT_REQUESTS: int = 10
    SEC_RATE_LIMIT_WINDOW: int = 1  # seconds

    # Attribution config path
    ATTRIBUTION_CONFIG_PATH: str = "config/attribution_config.json"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @field_validator("ADMIN_EMAIL")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """Validate email format - SEC requires valid contact email."""
        if not v:
            raise ValueError("ADMIN_EMAIL is required for SEC compliance")
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, v):
            raise ValueError(f"ADMIN_EMAIL must be a valid email address: {v}")
        return v

    @model_validator(mode="after")
    def validate_sec_user_agent(self):
        """
        Validate SEC User-Agent format is correct.
        Format must be: {APP_NAME} {ADMIN_EMAIL}
        """
        if not self.APP_NAME:
            raise ValueError("APP_NAME is required for SEC compliance")
        if not self.ADMIN_EMAIL:
            raise ValueError("ADMIN_EMAIL is required for SEC compliance")
        return self

    @property
    def sec_user_agent(self) -> str:
        """
        Generate SEC-compliant User-Agent string.
        Format: MAFinancingApp jgridley.mailinglists@gmail.com
        """
        return f"{self.APP_NAME} {self.ADMIN_EMAIL}"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance. Fails fast if config is invalid."""
    return Settings()
