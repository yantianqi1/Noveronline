import pytest

from app.utils.outbound_url import validate_base_url


def test_provider_url_requires_exact_https_allowlist():
    assert validate_base_url(
        "https://api.openai.com/v1/",
        allowed_hosts="api.openai.com",
    ) == "https://api.openai.com/v1"

    with pytest.raises(ValueError):
        validate_base_url("http://api.openai.com/v1", allowed_hosts="api.openai.com")
    with pytest.raises(ValueError):
        validate_base_url("https://evil.example/v1", allowed_hosts="api.openai.com")


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/v1",
    "https://169.254.169.254/latest/meta-data",
    "https://localhost/v1",
    "https://user:pass@api.openai.com/v1",
])
def test_provider_url_rejects_private_metadata_and_userinfo(url):
    with pytest.raises(ValueError):
        validate_base_url(url, allowed_hosts="api.openai.com,127.0.0.1")
