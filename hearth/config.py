"""Assumptions and secrets. Every default number lives in config/assumptions.yaml as {value, source, confirmed}."""
import os
from functools import cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ASSUMPTIONS = ROOT / "config" / "assumptions.yaml"
load_dotenv(ROOT / ".env")


@cache
def assumptions() -> dict:
    return yaml.safe_load(ASSUMPTIONS.read_text())


def a(path: str) -> Any:
    node = assumptions()
    for key in path.split("."):
        node = node[key]
    return node["value"]


def anthropic_headers() -> dict:
    return {"anthropic-workspace-id": os.environ["ANTHROPIC_WORKSPACE_ID"]}
