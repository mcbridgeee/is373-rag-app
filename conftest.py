"""Isolated test app; never use real runtime data, signing keys or a model download."""

import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

# Tests use the word-hashing embedder, so no model is downloaded.
os.environ.setdefault("RAG_EMBEDDER", "hash")
os.environ.pop("GROQ_API_KEY", None)

from app.main import create_app  # pylint: disable=wrong-import-position
from app.settings import Settings  # pylint: disable=wrong-import-position

ROOT = Path(__file__).resolve().parent


@pytest.fixture
def settings(tmp_path):
    """An explicit loopback test environment with a disposable database/key."""
    return Settings(
        mode="development",
        origin="http://127.0.0.1:8000",
        database=Path(tmp_path) / "test.sqlite3",
        secret="test-only-" + "a" * 48,
        corpus=ROOT / "corpus",
    )


@pytest.fixture
def client(settings):
    """Drive HTTP through the real app and isolated SQLite services."""
    with TestClient(create_app(settings), base_url=settings.origin) as browser:
        yield browser
