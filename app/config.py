from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    llm_api_key: str = ""
    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = Field(default=90, ge=1, le=300)
    demo_mode: bool = False
    image_provider: str = "mock"
    image_api_key: str = ""
    image_api_base_url: str = "https://api.openai.com/v1"
    image_model: str = "gpt-image-2.5-flare"
    image_timeout_seconds: float = Field(default=180, ge=1, le=600)
    asset_dir: str = "data/assets"
