import pytest

import hearth.config  # noqa: F401  loads .env first, so the deletions below win

# .env holds the hosted site's settings; tests run as the local API (no password, no Supabase), must never send a
# real call or text, and never need a real secret
HOSTED = ("HEARTH_VOICE_SECRET", "PHOTON_WEBHOOK_SECRET", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID",
          "PHOTON_PROJECT_ID", "PHOTON_PROJECT_API_KEY",
          "HEARTH_DEMO_CALLERS", "HEARTH_ALERT_PHONES", "HEARTH_BUILDING_PHONES",
          "HEARTH_PASSWORD", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "HEARTH_DATABASE_URL", "HEARTH_WEB_ORIGIN_REGEX")


@pytest.fixture(autouse=True)
def no_hosted_phone_line(monkeypatch):
    for k in HOSTED:
        monkeypatch.delenv(k, raising=False)
