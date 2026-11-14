import pytest

import hearth.config  # noqa: F401  loads .env first, so the deletions below win

# .env holds the hosted phone line's settings; tests must never send a real call or text, or need a real secret
HOSTED = ("HEARTH_VOICE_SECRET", "PHOTON_WEBHOOK_SECRET", "ELEVENLABS_AGENT_ID", "ELEVENLABS_PHONE_NUMBER_ID",
          "PHOTON_PROJECT_ID", "PHOTON_PROJECT_API_KEY")


@pytest.fixture(autouse=True)
def no_hosted_phone_line(monkeypatch):
    for k in HOSTED:
        monkeypatch.delenv(k, raising=False)
