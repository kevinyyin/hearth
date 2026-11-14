"""Private files the hosted API reads from Supabase Storage instead of its bundle: the CoStar-derived building index,
the county replay and the county patient file. Each is downloaded once into a writable cache and read from there.

python -m hearth.remote upload <local path> <storage path>   (uses SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)
"""
import os
import sys
from pathlib import Path

import httpx

from hearth.config import DATA

BUCKET = "hearth-private"  # private: sponsor-derived data never goes in a public bucket
CACHE = DATA / "remote"


def _cfg() -> tuple[str, dict] | None:
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not (url and key):
        return None
    # new secret keys (sb_secret_...) are not JWTs and go only in apikey; legacy service_role JWTs also go as a bearer
    return url.rstrip("/") + "/storage/v1", ({"apikey": key} if key.startswith("sb_") else {"Authorization": f"Bearer {key}", "apikey": key})


def _local(path: str) -> Path:
    out = (CACHE / path).resolve()
    if not out.is_relative_to(CACHE.resolve()):
        raise ValueError(f"bad storage path: {path!r}")
    return out


def fetch(path: str) -> Path | None:
    """The cached copy of `path` from the private bucket, downloading it the first time; None if absent or unconfigured."""
    out = _local(path)
    if out.exists():
        return out
    if (cfg := _cfg()) is None:
        return None
    r = httpx.get(f"{cfg[0]}/object/{BUCKET}/{path}", headers=cfg[1], timeout=60)
    if r.status_code in (400, 404):  # Supabase answers 400 for a missing object
        return None
    r.raise_for_status()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return out


def listdir(prefix: str) -> list[str]:
    """Names directly under `prefix` in the private bucket ([] if unconfigured)."""
    if (cfg := _cfg()) is None:
        return []
    r = httpx.post(f"{cfg[0]}/object/list/{BUCKET}", headers=cfg[1], json={"prefix": prefix, "limit": 1000}, timeout=30)
    r.raise_for_status()
    return [o["name"] for o in r.json()]


def upload(local: Path, path: str) -> None:
    cfg = _cfg()
    if cfg is None:
        raise SystemExit("set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
    httpx.post(f"{cfg[0]}/bucket", headers=cfg[1], json={"id": BUCKET, "name": BUCKET, "public": False}, timeout=30)  # exists: ignored
    files = [local] if local.is_file() else sorted(f for f in local.rglob("*") if f.is_file())
    for f in files:
        dest = path if local.is_file() else f"{path}/{f.relative_to(local).as_posix()}"
        r = httpx.post(f"{cfg[0]}/object/{BUCKET}/{dest}", headers=cfg[1] | {"x-upsert": "true"}, content=f.read_bytes(), timeout=120)
        r.raise_for_status()
    print(f"uploaded {len(files)} file(s) to {BUCKET}/{path}")


if __name__ == "__main__":
    if sys.argv[1:2] != ["upload"] or len(sys.argv) != 4:
        raise SystemExit("usage: python -m hearth.remote upload <local path> <storage path>")
    upload(Path(sys.argv[2]), sys.argv[3])
