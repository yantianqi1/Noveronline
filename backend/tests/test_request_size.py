from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware.request_size import RequestSizeLimitMiddleware


def test_request_size_limit_rejects_large_content_length_before_handler() -> None:
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=4)

    @app.post("/upload")
    async def upload(request: Request):
        return {"body": (await request.body()).decode()}

    response = TestClient(app).post("/upload", content=b"12345")

    assert response.status_code == 413
    assert response.json()["error"] == "request body is too large"
