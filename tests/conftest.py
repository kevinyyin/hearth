import pytest


@pytest.fixture(autouse=True)
def no_hosted_settings(monkeypatch):
    """A developer's .env may hold the hosted site's settings; every test runs as the local API, with no password, no
    voice secret and no Supabase, unless it sets one itself."""
    for k in ("HEARTH_PASSWORD", "HEARTH_VOICE_SECRET", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "HEARTH_DATABASE_URL",
              "HEARTH_WEB_ORIGIN_REGEX"):
        monkeypatch.delenv(k, raising=False)
