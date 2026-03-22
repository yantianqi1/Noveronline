from app import create_app


def test_preflight_allows_private_network_requests():
    app = create_app()
    client = app.test_client()

    response = client.open(
        "/api/project/seed/extract",
        method="OPTIONS",
        headers={
            "Origin": "http://127.0.0.1:5174",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
            "Access-Control-Request-Private-Network": "true",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5174"
    assert response.headers["Access-Control-Allow-Private-Network"] == "true"
