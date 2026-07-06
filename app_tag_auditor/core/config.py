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
    FLASK_PORT: int = 8501
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
        
        if self.GOOGLE_OAUTH_REDIRECT_URI == "http://localhost:8501" and self.FLASK_PORT != 8501:
            self.GOOGLE_OAUTH_REDIRECT_URI = f"http://localhost:{self.FLASK_PORT}"

        if not os.path.isabs(self.TEMP_STORAGE_DIR):
            self.TEMP_STORAGE_DIR = os.path.abspath(os.path.join(project_root, self.TEMP_STORAGE_DIR))
            
        if not os.path.isabs(self.LOCAL_OUTPUT_PATH):
            self.LOCAL_OUTPUT_PATH = os.path.abspath(os.path.join(project_root, self.LOCAL_OUTPUT_PATH))

        # Dynamically fallback if JADX_PATH does not exist
        if self.JADX_PATH:
            if not os.path.exists(self.JADX_PATH):
                import shutil
                system_jadx = shutil.which("jadx")
                if system_jadx:
                    self.JADX_PATH = system_jadx
                else:
                    packaged_jadx = os.path.join(project_root, "jadx", "bin", "jadx")
                    if os.path.exists(packaged_jadx):
                        self.JADX_PATH = packaged_jadx
                    else:
                        # Fallback for bin/jadx folder structure
                        packaged_jadx_bin = os.path.join(project_root, "bin", "jadx", "bin", "jadx")
                        if os.path.exists(packaged_jadx_bin):
                            self.JADX_PATH = packaged_jadx_bin
                        else:
                            self.JADX_PATH = "jadx"
            
        return self

@lru_cache
def get_settings() -> Settings:
    """
    Returns a cached instance of the application Settings.
    """
    return Settings()

