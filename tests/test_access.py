"""Care-team access: therapists with access read and upload; admins manage access only."""

from pathlib import Path

from app import care, database, security

ROOT = Path(__file__).resolve().parents[1]
PASSPHRASE = "a long enough test passphrase"


def _account(client, username, admin=False):
    settings = client.app.state.settings
    security.signup(settings, username, PASSPHRASE)
    if admin:
        database.set_role(settings, username, "admin")


def _login(client, username):
    client.cookies.clear()
    token = client.get("/api/csrf").json()["csrf_token"]
    response = client.post(
        "/api/login",
        json={"username": username, "password": PASSPHRASE},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 200
    return client.get("/api/csrf").json()["csrf_token"]


def _form_token(page):
    return page.text.split('name="csrf_token" value="')[1].split('"')[0]


def test_therapist_without_access_is_refused(client):
    _account(client, "newtherapist")
    token = _login(client, "newtherapist")
    for path in ("/ask", "/sessions", "/sessions/S01", "/upload"):
        page = client.get(path)
        assert page.status_code == 403 and "Ask an admin" in page.text
    api = client.post(
        "/api/ask", json={"question": "sleep?"}, headers={"X-CSRF-Token": token}
    )
    assert api.status_code == 403


def test_admin_manages_access_but_cannot_read(client):
    _account(client, "boss", admin=True)
    _account(client, "therapist")
    token = _login(client, "boss")
    for path in ("/ask", "/sessions/S02", "/upload"):
        page = client.get(path)
        assert page.status_code == 403 and "manage access but" in page.text
    api = client.post(
        "/api/ask", json={"question": "sleep?"}, headers={"X-CSRF-Token": token}
    )
    assert api.status_code == 403

    page = client.get("/admin")
    assert page.status_code == 200 and "No access" in page.text
    granted = client.post(
        "/admin/access",
        data={
            "username": "therapist",
            "action": "grant",
            "csrf_token": _form_token(page),
        },
    )
    assert "can now see" in granted.text and "granted therapist" in granted.text
    assert care.has_access(client.app.state.settings, "therapist")

    removed = client.post(
        "/admin/access",
        data={
            "username": "therapist",
            "action": "remove",
            "csrf_token": _form_token(granted),
        },
    )
    assert "can no longer see" in removed.text and "removed therapist" in removed.text
    assert not care.has_access(client.app.state.settings, "therapist")


def test_admin_accounts_can_never_be_given_access(client):
    _account(client, "boss", admin=True)
    _account(client, "boss2", admin=True)
    token = _login(client, "boss")
    response = client.post(
        "/api/admin/access",
        json={"username": "boss2", "action": "grant"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 422


def test_therapists_cannot_change_access(client):
    _account(client, "therapist")
    care.change(client.app.state.settings, "test", "therapist", grant=True)
    token = _login(client, "therapist")
    response = client.post(
        "/api/admin/access",
        json={"username": "therapist", "action": "remove"},
        headers={"X-CSRF-Token": token},
    )
    assert response.status_code == 403
    assert care.has_access(client.app.state.settings, "therapist")


def _upload(client, name, content, token):
    return client.post(
        "/upload",
        data={"csrf_token": token},
        files={"transcript": (name, content, "text/markdown")},
    )


def test_upload_adds_replaces_and_ignores_repeats(client):
    _account(client, "therapist")
    care.change(client.app.state.settings, "test", "therapist", grant=True)
    _login(client, "therapist")
    page = client.get("/upload")
    original = (ROOT / "corpus" / "S06.md").read_bytes()

    same = _upload(client, "S06.md", original, _form_token(page))
    assert same.status_code == 200 and "Nothing changed" in same.text
    count = client.app.state.rag.chunk_count()

    shorter = original[: original.index(b"[00:02:30]")]
    replaced = _upload(client, "S06.md", shorter, _form_token(same))
    assert "Replaced S06" in replaced.text
    assert client.app.state.rag.chunk_count() < count

    added = _upload(
        client,
        "S07.md",
        original.replace(b"id: S06", b"id: S07"),
        _form_token(replaced),
    )
    assert "Added S07" in added.text
    assert client.get("/sessions/S07").status_code == 200


def test_upload_rejects_bad_files(client):
    _account(client, "therapist")
    care.change(client.app.state.settings, "test", "therapist", grant=True)
    _login(client, "therapist")
    token = _form_token(client.get("/upload"))
    assert "Markdown" in _upload(client, "notes.txt", b"hi", token).text
    assert "frontmatter" in _upload(client, "x.md", b"no frontmatter", token).text
    too_big = b"---\nid: S08\n---\n" + b"x" * 200_001
    assert "200 KB" in _upload(client, "big.md", too_big, token).text
    missing_csrf = _upload(client, "S06.md", b"x", "wrong")
    assert missing_csrf.status_code == 403


def test_logged_out_upload_goes_to_login(client):
    response = client.post(
        "/upload",
        files={"transcript": ("S06.md", b"x", "text/markdown")},
        follow_redirects=False,
    )
    assert response.status_code == 303 and response.headers["location"] == "/login"
