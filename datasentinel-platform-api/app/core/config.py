from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://datasentinel:datasentinel_dev@localhost:5432/datasentinel"
    DB_HOST: str = ""
    DB_USER: str = "datasentinel"
    DB_PASSWORD: str = ""
    DB_NAME: str = "datasentinel"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ENVIRONMENT: str = "development"
    UPLOAD_DIR: str = "./uploads"

    AWS_REGION: str = "eu-west-1"
    S3_DATASETS_BUCKET: str = ""
    S3_MODELS_BUCKET: str = ""
    SQS_DQA_REQUESTED_URL: str = ""
    SQS_DQA_COMPLETED_URL: str = ""
    SQS_CORRECTION_REQUESTED_URL: str = ""
    SQS_CORRECTION_COMPLETED_URL: str = ""
    SQS_AI_PREDICT_REQUESTED_URL: str = ""
    SQS_AI_TRAINING_TRIGGERED_URL: str = ""
    INTERNAL_MESSAGE_SIGNING_KEY: str = "dev-internal-signing-key-change-in-production"
    DQA_EXECUTION_MODE: str = "inprocess"
    CORRECTION_EXECUTION_MODE: str = "inprocess"

    class Config:
        env_file = ".env"

    def resolved_database_url(self) -> str:
        if self.DB_HOST and self.DB_PASSWORD:
            return (
                f"postgresql://{self.DB_USER}:{self.DB_PASSWORD}"
                f"@{self.DB_HOST}:5432/{self.DB_NAME}"
            )
        return self.DATABASE_URL


@lru_cache()
def get_settings():
    return Settings()


settings = get_settings()
