"""MiroFish-Novel FastAPI application factory."""

from fastapi.testclient import TestClient


def create_app():
    from .main import create_app as create_fastapi_app

    app = create_fastapi_app()
    _attach_test_compat(app)
    return app


class _FastApiCompatClient:
    def __init__(self, app):
        self.client = TestClient(app)

    def get(self, url, query_string=None, **kwargs):
        return _CompatResponse(self.client.get(url, params=query_string, **_client_kwargs(kwargs)))

    def delete(self, url, query_string=None, **kwargs):
        return _CompatResponse(self.client.delete(url, params=query_string, **_client_kwargs(kwargs)))

    def patch(self, url, json=None, **kwargs):
        return _CompatResponse(self.client.patch(url, json=json, **_client_kwargs(kwargs)))

    def put(self, url, json=None, data=None, **kwargs):
        return _CompatResponse(self.client.put(url, json=json or data, **_client_kwargs(kwargs)))

    def post(self, url, json=None, data=None, content_type=None, **kwargs):
        request_kwargs = _client_kwargs(kwargs)
        if content_type == "multipart/form-data" and isinstance(data, dict):
            fields, files = _multipart_payload(data)
            return _CompatResponse(self.client.post(url, data=fields, files=files, **request_kwargs))
        return _CompatResponse(self.client.post(url, json=json if json is not None else data, **request_kwargs))

    def open(self, url, method="GET", headers=None, data=None, content_type=None, **kwargs):
        if method.upper() == "OPTIONS":
            return _CompatResponse(self.client.options(url, headers=headers, **_client_kwargs(kwargs)))
        if method.upper() == "POST":
            return self.post(url, data=data, content_type=content_type, headers=headers, **kwargs)
        return _CompatResponse(self.client.request(method, url, headers=headers, **_client_kwargs(kwargs)))


class _CompatResponse:
    def __init__(self, response):
        self._response = response
        self.status_code = response.status_code
        self.data = response.content
        self.headers = response.headers

    def get_json(self):
        return self._response.json()


class _DummyContext:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _attach_test_compat(app) -> None:
    app.test_client = lambda: _FastApiCompatClient(app)
    app.app_context = lambda: _DummyContext()


def _client_kwargs(kwargs: dict) -> dict:
    allowed = {"headers", "params", "cookies", "timeout"}
    return {key: value for key, value in kwargs.items() if key in allowed}


def _multipart_payload(data: dict) -> tuple[dict, dict]:
    fields = {}
    files = {}
    for key, value in data.items():
        if isinstance(value, tuple) and len(value) == 2:
            file_obj, filename = value
            files[key] = (filename, file_obj, "application/octet-stream")
        else:
            fields[key] = value
    return fields, files
