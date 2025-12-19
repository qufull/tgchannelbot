from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_PATH = Path(__file__).resolve().parents[3] / ".env"

class Settings(BaseSettings):

    BOT_TOKEN: str

    API_ID: int
    API_HASH: str
    PHONE: str

    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DB_NAME: str

    ADMIN_IDS: List[int]

    ANTHROPIC_API_KEY: str = ""

    model_config = SettingsConfigDict(env_file=ENV_PATH)

    @field_validator("ADMIN_IDS", mode="before")
    @classmethod
    def parse_admin_ids(cls, v):
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(",") if x.strip()]
        if isinstance(v, int):
            return [v]
        return [int(v)]

    @property
    def DATABASE_URL_asyncpg(self):
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB_NAME}"

    @property
    def userbot_enabled(self) -> bool:
        return bool(self.API_ID and self.API_HASH and self.PHONE)

settings = Settings()