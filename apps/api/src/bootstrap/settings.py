from pydantic_settings import BaseSettings, SettingsConfigDict


class DbSettings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"
    database: str = "mirofish"

    model_config = SettingsConfigDict(
        env_prefix="MIROFISH_DB_",
        env_file=".env",
        extra="ignore",
    )

    @property
    def sqlalchemy_dsn(self) -> str:
        return f"postgresql+psycopg://{self.user}:{self.password}@{self.host}:{self.port}/{self.database}"


class ObjectStorageSettings(BaseSettings):
    endpoint: str = "127.0.0.1:9000"
    access_key: str = "minioadmin"
    secret_key: str = "minioadmin"
    bucket: str = "mirofish-artifacts"
    secure: bool = False

    model_config = SettingsConfigDict(
        env_prefix="MIROFISH_MINIO_",
        env_file=".env",
        extra="ignore",
    )


class LlmFacilitySettings(BaseSettings):
    default_timeout_seconds: int = 60
    activity_buffer_size: int = 200
    request_audit_enabled: bool = True

    model_config = SettingsConfigDict(
        env_prefix="MIROFISH_LLM_",
        env_file=".env",
        extra="ignore",
    )


class AppSettings(BaseSettings):
    app_name: str = "MiroFish-Novel API v2"
    api_prefix: str = "/api/v2"
    env: str = "development"
    host: str = "127.0.0.1"
    port: int = 5102
    redis_url: str = "redis://127.0.0.1:6379/0"
    temporal_target: str = "127.0.0.1:7233"
    database_url_override: str | None = None

    model_config = SettingsConfigDict(
        env_prefix="MIROFISH_",
        env_file=".env",
        extra="ignore",
    )

    @property
    def db(self) -> DbSettings:
        return DbSettings()

    @property
    def object_storage(self) -> ObjectStorageSettings:
        return ObjectStorageSettings()

    @property
    def llm_facility(self) -> LlmFacilitySettings:
        return LlmFacilitySettings()

    @property
    def postgres_dsn(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return self.db.sqlalchemy_dsn

    @property
    def minio_endpoint(self) -> str:
        return self.object_storage.endpoint

    @property
    def minio_access_key(self) -> str:
        return self.object_storage.access_key

    @property
    def minio_secret_key(self) -> str:
        return self.object_storage.secret_key
