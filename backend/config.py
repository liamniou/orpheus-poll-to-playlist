"""Configuration settings for the Orpheus Poll Downloader."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Orpheus Network credentials
    orpheus_api_key: str = Field(default="", env="ORPHEUS_API_KEY")
    orpheus_session_cookie: str = Field(default="", env="ORPHEUS_SESSION_COOKIE")
    
    # Application settings
    app_host: str = Field(default="0.0.0.0", env="APP_HOST")
    app_port: int = Field(default=7575, env="APP_PORT")
    
    # Database
    database_url: str = Field(default="sqlite:///./data/orpheus_poll.db", env="DATABASE_URL")
    
    # Cache settings (default 12 hours = 720 minutes)
    cache_ttl_minutes: int = Field(default=720, env="CACHE_TTL_MINUTES")
    
    # Download directory
    download_dir: str = Field(default="./downloads", env="DOWNLOAD_DIR")
    
    # qBittorrent settings
    qbit_url: str = Field(default="", env="QBIT_URL")
    qbit_user: str = Field(default="", env="QBIT_USER")
    qbit_password: str = Field(default="", env="QBIT_PASSWORD")
    qbit_category: str = Field(default="orpheus", env="QBIT_CATEGORY")
    
    # Navidrome settings (Subsonic API)
    navidrome_url: str = Field(default="", env="NAVIDROME_URL")
    navidrome_user: str = Field(default="", env="NAVIDROME_USER")
    navidrome_password: str = Field(default="", env="NAVIDROME_PASSWORD")
    navidrome_library_id: int = Field(default=1, env="NAVIDROME_LIBRARY_ID")
    # The music folder path as Navidrome sees it (may differ from qBit's save_path).
    # Used to build targeted scan paths. Leave empty to use qBit's save_path as-is.
    navidrome_music_folder: str = Field(default="", env="NAVIDROME_MUSIC_FOLDER")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# Ensure directories exist
os.makedirs(os.path.dirname(settings.database_url.replace("sqlite:///", "")) or "./data", exist_ok=True)
os.makedirs(settings.download_dir, exist_ok=True)
