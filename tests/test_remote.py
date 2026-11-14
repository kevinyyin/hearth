import httpx
import pytest

from hearth import remote


class Resp:
    def __init__(self, status, body=b""):
        self.status_code, self.content = status, body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("bad", request=None, response=None)


@pytest.fixture(autouse=True)
def configured(monkeypatch, tmp_path):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-key")
    monkeypatch.setattr(remote, "CACHE", tmp_path)


def test_fetch_downloads_once_then_reads_the_cache(monkeypatch):
    calls = []
    monkeypatch.setattr(remote.httpx, "get", lambda url, **k: calls.append(url) or Resp(200, b"{}"))
    p1, p2 = remote.fetch("results/r1/meta.json"), remote.fetch("results/r1/meta.json")
    assert p1 == p2 and p1.read_bytes() == b"{}" and len(calls) == 1 and "/storage/v1/object/" in calls[0]


def test_missing_object_is_none(monkeypatch):
    monkeypatch.setattr(remote.httpx, "get", lambda url, **k: Resp(400))  # Supabase answers 400 for a missing object
    assert remote.fetch("results/nope/meta.json") is None


def test_not_configured_is_none(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL")
    assert remote.fetch("anything.json") is None


def test_paths_cannot_escape_the_cache():
    with pytest.raises(ValueError):
        remote.fetch("../../etc/passwd")


def test_new_secret_keys_go_only_in_the_apikey_header(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sb_secret_abc")
    seen = {}
    monkeypatch.setattr(remote.httpx, "get", lambda url, headers, **k: seen.update(headers) or Resp(200, b"x"))
    remote.fetch("a.json")
    assert seen == {"apikey": "sb_secret_abc"}
