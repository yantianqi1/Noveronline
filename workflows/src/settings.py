from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    temporal_target: str = "127.0.0.1:7233"
    temporal_namespace: str = "default"
    task_queue: str = "mirofish-main"
    worker_name: str = "mirofish-novel-worker"

    model_config = SettingsConfigDict(env_prefix="MIROFISH_", extra="ignore")
