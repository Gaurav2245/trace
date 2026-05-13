from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_NAME: str = "TRACE_PD"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"

    DATABASE_URL: str = (
        "postgresql+asyncpg://trcpd_user:trcpd_pass_2024@localhost:15432/trcpd_db"
    )
    SECRET_KEY: str = "trcpd_jwt_secret_change_me_in_prod_2024"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    CORS_ORIGINS: str = (
        "http://localhost:13000,http://localhost:18000,"
        "http://localhost:5173,http://localhost:3000,"
        "http://localhost:10080"
    )

    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_VERSION: str = "2024-10-21"
    AZURE_OPENAI_DEPLOYMENT: str = ""
    AZURE_DEPLOYMENT_GPT4O: str = ""
    OPENAI_TEMPERATURE: float = 0.7

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def azure_openai_deployment_name(self) -> str:
        return self.AZURE_OPENAI_DEPLOYMENT or self.AZURE_DEPLOYMENT_GPT4O or "gpt-4o-mini"

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
