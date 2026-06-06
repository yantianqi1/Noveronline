from bootstrap import WorkerBootstrap, build_worker_bootstrap
from settings import WorkerSettings


def describe_worker() -> dict[str, object]:
    return build_worker_bootstrap().as_dict()


def load_worker_settings() -> WorkerSettings:
    return WorkerSettings()


def load_worker_bootstrap() -> WorkerBootstrap:
    return build_worker_bootstrap(load_worker_settings())
