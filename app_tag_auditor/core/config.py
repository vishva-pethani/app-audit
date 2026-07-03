import os
from functools import lru_cache
from typing import Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "app_tag_auditor/.env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    GOOGLE_OAUTH_CLIENT_ID: Optional[str] = None
    GOOGLE_OAUTH_CLIENT_SECRET: Optional[str] = None
    GOOGLE_OAUTH_REDIRECT_URI: str = "http://localhost:8501"
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

    @model_validator(mode="after")
    def resolve_absolute_paths(self) -> "Settings":
        # Resolve paths relative to the project root directory (parent of 'core' folder)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        if not os.path.isabs(self.TEMP_STORAGE_DIR):
            self.TEMP_STORAGE_DIR = os.path.abspath(os.path.join(project_root, self.TEMP_STORAGE_DIR))
            
        if not os.path.isabs(self.LOCAL_OUTPUT_PATH):
            self.LOCAL_OUTPUT_PATH = os.path.abspath(os.path.join(project_root, self.LOCAL_OUTPUT_PATH))
            
        return self

@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached instance of the application Settings.
    """
    return Settings()

