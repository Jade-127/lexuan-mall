"""全局配置：统一从 .env 读取，禁止硬编码 Key。"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # 阿里云百炼（OpenAI 兼容模式）
    dashscope_api_key: str = ""
    openai_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    chat_model: str = "qwen-plus"
    embed_model: str = "text-embedding-v3"

    # 服务
    app_name: str = "lexuan-agent"
    app_port: int = 8087

    # 下游 Java 服务
    item_service_url: str = "http://127.0.0.1:8080"
    trade_service_url: str = "http://127.0.0.1:8080"


settings = Settings()
