import pytest


@pytest.fixture(autouse=True)
def no_hosted_password(monkeypatch):
    """A developer's .env may hold the hosted site's HEARTH_PASSWORD; tests run as the local, password-less API unless
    they set one themselves."""
    monkeypatch.delenv("HEARTH_PASSWORD", raising=False)
