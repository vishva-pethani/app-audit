from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = None
    GOOGLE_OAUTH_CLIENT_SECRET: Optional[str] = None
    GOOGLE_API_KEY: Optional[str] = None
    LOCAL_OUTPUT_PATH: str = "./output/audit_results.xlsx"
    JADX_PATH: str = "jadx"
    APPIUM_SERVER_URL: str = "http://localhost:4723"
    ANDROID_APP_PACKAGE: Optional[str] = None
    TEMP_STORAGE_DIR: str = "./tmp"
    LLM_PROVIDER: str = "anthropic"
    RUNTIME_CAPTURE_BUFFER_SECONDS: float = 3.0


    ANTHROPIC_API_KEY: Optional[str] = None
    COMPANY_LLM_GATEWAY_URL: Optional[str] = None
    COMPANY_LLM_GATEWAY_API_KEY: Optional[str] = None

@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached instance of the application Settings.
    """
    return Settings()
