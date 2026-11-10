from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_preflight_rejects_unconfigured_origin_and_private_network_header(tmp_path):
    app = create_app(settings=Settings(
        DATABASE_URL=f"sqlite:///{tmp_path / 'db.sqlite'}",
        UPLOAD_FOLDER=str(tmp_path / "uploads"),
        CORS_ALLOWED_ORIGINS="",
    ))
    client = TestClient(app)

    response = client.request(
        "OPTIONS",
        "/api/project/seed/extract",
        headers={
            "Origin": "http://127.0.0.1:5174",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            "Access-Control-Request-Private-Network": "true",
        },
    )

    assert response.status_code == 400
    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Access-Control-Allow-Private-Network" not in response.headers


def test_preflight_allows_only_explicit_origin_without_private_network(tmp_path):
    app = create_app(settings=Settings(
        DATABASE_URL=f"sqlite:///{tmp_path / 'db.sqlite'}",
        UPLOAD_FOLDER=str(tmp_path / "uploads"),
        CORS_ALLOWED_ORIGINS="http://127.0.0.1:5174",
    ))
    response = TestClient(app).options(
        "/api/project/seed/extract",
        headers={
            "Origin": "http://127.0.0.1:5174",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5174"
    assert "Access-Control-Allow-Private-Network" not in response.headers
