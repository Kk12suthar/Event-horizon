"""
Configuration settings for the FastAPI backend
"""

from pydantic_settings import BaseSettings
from typing import List
import os

class Settings(BaseSettings):
    """Application settings"""
    
    # API Configuration
    app_name: str = "ELK.js Process Mining API"
    version: str = "1.0.0"
    debug: bool = False
    
    # CORS Configuration
    allowed_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    # Database Configuration (if needed in future)
    database_url: str = "sqlite:///./process_mining.db"
    
    # File Storage
    upload_dir: str = "./uploads"
    max_file_size: int = 10 * 1024 * 1024  # 10MB
    
    # ELK Configuration
    elk_timeout: int = 30  # seconds
    # No limits on nodes or edges - process unlimited data
    
    # Export Configuration
    export_dir: str = "./exports"
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"

# Create settings instance
settings = Settings()
