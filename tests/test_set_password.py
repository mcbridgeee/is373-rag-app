"""Changing a password: new one works, old one and open sessions stop working."""

import pytest

from app import database, manage, security

OLD = "the original demo passphrase"
NEW = "a brand new longer passphrase"


def _login(client, username, password):
    client.cookies.clear()
    token = client.get("/api/csrf").json()["csrf_token"]
    return client.post(
        "/api/login",
        json={"username": username, "password": password},
        headers={"X-CSRF-Token": token},
    )


def _open_sessions(settings, username):
    with database.connect(settings) as connection:
        return connection.execute(
            """SELECT COUNT(*) FROM sessions JOIN users ON users.id = sessions.user_id
               WHERE users.username = ? AND sessions.revoked = 0""",
            (username,),
        ).fetchone()[0]


def test_new_password_works_and_old_one_and_sessions_stop(client):
    settings = client.app.state.settings
    security.signup(settings, "therapist", OLD)
    assert _login(client, "therapist", OLD).status_code == 200
    assert _open_sessions(settings, "therapist") == 1

    assert security.set_password(settings, "therapist", NEW) is True

    assert _open_sessions(settings, "therapist") == 0
    assert _login(client, "therapist", OLD).status_code != 200
    assert _login(client, "therapist", NEW).status_code == 200


def test_short_password_and_unknown_user_are_refused(client):
    settings = client.app.state.settings
    security.signup(settings, "therapist", OLD)
    with pytest.raises(ValueError):
        security.set_password(settings, "therapist", "too short")
    assert security.set_password(settings, "nobody_here", NEW) is False
    assert _login(client, "therapist", OLD).status_code == 200


def test_manage_command_changes_the_password(client, monkeypatch, capsys):
    settings = client.app.state.settings
    security.signup(settings, "therapist", OLD)
    monkeypatch.setattr("app.manage.Settings.load", lambda: settings)
    monkeypatch.setenv("NEW_USER_PASSWORD", NEW)

    assert manage.main(["set-password", "therapist"]) == 0
    assert "password changed" in capsys.readouterr().out
    assert _login(client, "therapist", NEW).status_code == 200

    assert manage.main(["set-password", "nobody_here"]) == 1
    assert "No account named" in capsys.readouterr().err
