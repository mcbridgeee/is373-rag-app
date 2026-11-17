"""Retrieval and ask checks, mapped to the stories in the planning doc.

These run with the word-hashing test embedder, so they check the plumbing
(import, IDs, filters, access, citations), not real vector-search quality.
Q1-Q6 quality is measured with the real model by scripts/evaluate.py.
"""

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from app.main import create_app
from app.rag import answer as answering
from app.rag.corpus import exchange_chunks, fixed_chunks, load_directory, parse
from app.rag.store import Index, keyword_query

ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "a long enough test passphrase"


def _login(client):
    from app import security  # pylint: disable=import-outside-toplevel

    from app import care  # pylint: disable=import-outside-toplevel

    security.signup(client.app.state.settings, "therapist", PASSPHRASE)
    care.change(client.app.state.settings, "test-admin", "therapist", grant=True)
    token = client.get("/api/csrf").json()["csrf_token"]
    response = client.post(
        "/api/login",
        json={"username": "therapist", "password": PASSPHRASE},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    return client.get("/api/csrf").json()["csrf_token"]


# ---- import --------------------------------------------------------------


def test_frontmatter_is_metadata_and_never_indexed():
    """planted_content holds the answers; it must not reach any index."""
    transcripts = load_directory(ROOT / "corpus")
    assert [t.id for t in transcripts] == ["S01", "S02", "S03", "S04", "S05", "S06"]
    for transcript in transcripts:
        assert "planted_content" not in transcript.body
        assert transcript.body.startswith("[00:00:")
        assert set(transcript.meta) <= {
            "id",
            "document",
            "session_date",
            "client",
            "therapist",
        }
    s02 = next(t for t in transcripts if t.id == "S02")
    assert "sleep" not in s02.body.lower()


def test_exchange_chunks_keep_question_and_answer_together():
    transcript = load_directory(ROOT / "corpus")[1]
    chunks = exchange_chunks(transcript)
    assert chunks[0].id == "S02-C001"
    assert all(
        c.text.splitlines()[0].split("] ")[1].startswith("Dr. Thorne") for c in chunks
    )
    assert any("Jenny:" in c.text for c in chunks)
    assert {c.session_date for c in chunks} == {"2026-09-14"}


def test_fixed_chunks_are_about_500_characters():
    transcript = load_directory(ROOT / "corpus")[0]
    chunks = fixed_chunks(transcript)
    assert all(len(c.text) <= 500 for c in chunks)
    assert chunks[0].id == "S01-F001" and chunks[0].start == "00:00:06"


def test_bad_frontmatter_is_rejected():
    with pytest.raises(ValueError):
        parse("no frontmatter here")
    with pytest.raises(ValueError):
        parse("---\nid: nope\n---\n[00:00:01] A: hi")


def test_reimport_changes_nothing(tmp_path):
    """Story 4: importing the same transcript twice keeps the same chunks and IDs."""
    index = Index(tmp_path)
    first = index.import_directory(ROOT / "corpus")
    count, ids = index.chunk_count(), index.chunk_ids()
    second = index.import_directory(ROOT / "corpus")
    assert set(first.values()) == {"added"}
    assert set(second.values()) == {"unchanged"}
    assert index.chunk_count() == count and index.chunk_ids() == ids
    assert index._collection("exchange").count() == index.chunk_count("exchange")


def test_changed_transcript_replaces_its_old_chunks(tmp_path):
    index = Index(tmp_path)
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    original = (ROOT / "corpus" / "S06.md").read_text()
    (corpus / "S06.md").write_text(original)
    index.import_directory(corpus)
    shorter = original[: original.index("[00:02:30]")]
    (corpus / "S06.md").write_text(shorter)
    assert index.import_directory(corpus) == {"S06": "updated"}
    assert index._collection("exchange").count() == index.chunk_count("exchange")
    assert all(c.start < "00:02:30" for c in index.session("S06")[1])


# ---- retrieval -----------------------------------------------------------


def test_keyword_baseline_misses_s02_for_sleep(tmp_path):
    """The Q2 trap: the keyword baseline can't find 'up until 3 a.m.'."""
    index = Index(tmp_path)
    index.import_directory(ROOT / "corpus")
    sessions = {h.chunk.session_id for h in index.keyword("trouble sleeping", k=20)}
    assert "S02" not in sessions
    assert {"S04", "S05", "S06"} <= sessions


def test_keyword_finds_exact_terms(tmp_path):
    index = Index(tmp_path)
    index.import_directory(ROOT / "corpus")
    hits = index.keyword("Has the client mentioned sertraline?", k=10)
    assert hits and hits[0].chunk.session_id in {"S03", "S04", "S05", "S06"}
    assert index.keyword("What is the client's diagnosis?") == []


def test_keyword_query_ignores_punctuation_and_operators():
    assert keyword_query('sleep" OR NEAR(x') == '"sleep" OR "near"'
    assert keyword_query("has the client") == ""


def test_vector_search_filters_by_session_range(tmp_path):
    index = Index(tmp_path)
    index.import_directory(ROOT / "corpus")
    hits = index.vector("sister Ashley", k=5, sessions=(4, 6))
    assert hits and all(4 <= h.chunk.session_number <= 6 for h in hits)


# ---- answers -------------------------------------------------------------


def _hits(tmp_path):
    index = Index(tmp_path)
    index.import_directory(ROOT / "corpus")
    return index.keyword("sertraline", k=3)


def test_no_passages_means_not_mentioned(tmp_path):
    result = answering.answer("What is the client's diagnosis?", [])
    assert result.text == answering.NOT_MENTIONED and not result.generated


def test_without_a_key_the_passages_are_still_shown(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    hits = _hits(tmp_path)
    result = answering.answer("sertraline?", hits)
    assert not result.generated and result.hits == hits


def test_invented_citations_are_flagged(tmp_path):
    hits = _hits(tmp_path)
    real = hits[0].chunk.id
    result = answering.answer(
        "sertraline?",
        hits,
        generate=lambda q, h: f"Started it [{real}], dose doubled [S09-C001].",
    )
    assert result.cited == [real]
    assert any("S09-C001" in w for w in result.warnings)


def test_uncited_answers_are_flagged(tmp_path):
    result = answering.answer(
        "x", _hits(tmp_path), generate=lambda q, h: "She has panic disorder."
    )
    assert any("no citations" in w for w in result.warnings)


def test_citations_become_link_segments():
    pieces = answering.segments("Yes [S02-C004] and later [S05-C002].")
    assert ("S02-C004", "S02-C004") in pieces and pieces[0] == ("Yes ", None)


# ---- pages and access ----------------------------------------------------


def test_logged_out_visitors_cannot_ask_or_read(client):
    """Story 5: only logged-in users see transcripts or ask."""
    assert client.post("/api/ask", json={"question": "sleep?"}).status_code == 401
    for path in ("/ask", "/sessions", "/sessions/S02"):
        response = client.get(path, follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == "/login"


def test_ask_api_returns_passages_with_session_links(client):
    """Story 2: every passage links to its session and exchange."""
    token = _login(client)
    response = client.post(
        "/api/ask",
        json={"question": "Has she mentioned sertraline?", "method": "keyword"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["passages"]
    first = body["passages"][0]
    assert first["url"] == f"/sessions/{first['session']}#{first['id']}"
    page = client.get(f"/sessions/{first['session']}")
    assert f'id="{first["id"]}"' in page.text


def test_ask_api_rejects_extra_fields_and_needs_csrf(client):
    token = _login(client)
    assert client.post("/api/ask", json={"question": "sleep?"}).status_code == 403
    bad = client.post(
        "/api/ask",
        json={"question": "sleep?", "method": "vector", "k": 50},
        headers={"X-CSRF-Token": token},
    )
    assert bad.status_code == 422


def test_ask_form_shows_answer_and_passages(client):
    _login(client)
    page = client.get("/ask")
    token = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post(
        "/ask",
        data={"question": "sertraline", "method": "keyword", "csrf_token": token},
    )
    assert response.status_code == 200
    assert "Passages retrieved" in response.text and "S03-C" in response.text


def test_sessions_list_and_unknown_session(client):
    _login(client)
    assert "Session 6 transcript" in client.get("/sessions").text
    assert client.get("/sessions/S99").status_code == 404


def test_hosted_signup_is_closed(settings):
    closed = replace(settings, allow_signup=False)
    with TestClient(create_app(closed), base_url=closed.origin) as browser:
        assert browser.get("/signup").status_code == 403
        token = browser.get("/api/csrf").json()["csrf_token"]
        response = browser.post(
            "/api/signup",
            json={"username": "someone", "password": PASSPHRASE},
            headers={"X-CSRF-Token": token},
        )
        assert response.status_code == 403
