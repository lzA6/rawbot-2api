from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding='utf-8',
        extra="ignore"
    )

    APP_NAME: str = "rawbot-2api"
    APP_VERSION: str = "1.2.0"
    DESCRIPTION: str = "一个将 rawbot.org 的多模型比较功能聚合为单一 API 的高性能代理 (已移除 OpenAI)。"

    # --- 安全与部署 ---
    API_MASTER_KEY: Optional[str] = None
    NGINX_PORT: int = 8090

    # --- 下游凭证 ---
    COHERE_TOKEN: Optional[str] = None
    AI21_TOKEN: Optional[str] = None
    MISTRAL_TOKEN: Optional[str] = None

    # --- API 行为 ---
    API_REQUEST_TIMEOUT: int = 120

    # --- 模型定义 ---
    VIRTUAL_MODEL: str = "rawbot-omnibus"
    KNOWN_MODELS: List[str] = [
        "rawbot-omnibus",
        "command-r-08-2024",
        "jamba-mini",
        "mistral-small-latest"
    ]

settings = Settings()
