from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "exam-platform"
    environment: str = "local"
    debug: bool = True

    mongo_port: int = 27017
    mongo_host: str = "localhost"
    mongo_db: str = "exams_platform"
    mongo_password: str | None = None
    mongo_params: str | None = None
    mongo_user: str | None = None

    jwt_algorithm: str = "HS256"
    jwt_secret_key: str = "very-secret-key"
    access_token_expires_minutes: int = 1
    refresh_token_expires_days: int = 7

    redis_db: int = 0
    redis_port: int = 6379
    redis_host: str = "localhost"
    redis_password: str | None = None

    model_config = SettingsConfigDict(env_file=(".env",), case_sensitive=True)

    @property
    def mongo_uri(self) -> str:
        auth = ""
        if self.mongo_user and self.mongo_password:
            auth = f"{self.mongo_user}:{self.mongo_password}@"
        params = f"?retryWrites=true&w=majority"
        return f"mongodb+srv://{auth}{self.mongo_host}/{self.mongo_db}{params}"


settings = Settings()
