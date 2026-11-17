"""Who may see a client's transcripts.

- Therapists (the "member" role) read, ask about and upload transcripts, but
  only for clients they have been given access to.
- Admins manage that access. They cannot open transcripts or ask questions.
- Clients have no accounts.
- Every grant and removal is logged with who made it and when.

The demo has one fictional client. Sharing a client with another provider
(a psychiatrist or a PCP) would need the client's recorded consent, a release
of information; that is documented as future work, not built.
"""

import time

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from app import security
from app.database import connect

CLIENT = {"id": "C01", "name": "Jenny Alvarez", "label": "Jenny Alvarez (fictional)"}
ADMIN_NO_READ = "Admins manage access but can't read transcripts."
NO_ACCESS = "You don't have access to this client yet. Ask an admin to add you."

SCHEMA = """
CREATE TABLE IF NOT EXISTS care_team (
    client_id TEXT NOT NULL,
    username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    granted_by TEXT NOT NULL,
    granted_at INTEGER NOT NULL,
    PRIMARY KEY (client_id, username)
);
CREATE TABLE IF NOT EXISTS access_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at INTEGER NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('granted', 'removed')),
    client_id TEXT NOT NULL,
    username TEXT NOT NULL
);
"""


def has_access(settings, username: str, client_id: str = CLIENT["id"]) -> bool:
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT 1 FROM care_team WHERE client_id = ? AND username = ?",
            (client_id, username),
        ).fetchone()
    return row is not None


def team(settings, client_id: str = CLIENT["id"]) -> set[str]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT username FROM care_team WHERE client_id = ?", (client_id,)
        ).fetchall()
    return {row["username"] for row in rows}


def change(settings, actor: str, username: str, grant: bool) -> bool:
    """Grant or remove a therapist's access. Returns False if nothing changed.

    Only therapist accounts can be added: an admin account can never be
    given transcript access, even by another admin.
    """
    username = username.strip().lower()
    with connect(settings) as connection:
        row = connection.execute(
            "SELECT role FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            raise ValueError("No account has that username.")
        if grant and row["role"] != "member":
            raise ValueError("Only therapist accounts can be given access.")
        if grant:
            result = connection.execute(
                "INSERT OR IGNORE INTO care_team VALUES (?, ?, ?, ?)",
                (CLIENT["id"], username, actor, int(time.time())),
            )
        else:
            result = connection.execute(
                "DELETE FROM care_team WHERE client_id = ? AND username = ?",
                (CLIENT["id"], username),
            )
        if result.rowcount != 1:
            return False
        connection.execute(
            "INSERT INTO access_log (at, actor, action, client_id, username) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                int(time.time()),
                actor,
                "granted" if grant else "removed",
                CLIENT["id"],
                username,
            ),
        )
    return True


def history(settings, limit: int = 20) -> list[dict]:
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT at, actor, action, username FROM access_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [
        {
            **dict(row),
            "when": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(row["at"])),
        }
        for row in rows
    ]


def require_care(request: Request) -> dict:
    """API dependency: a therapist on this client's care team, checked every request."""
    user = security.require_user(request)
    if user["role"] == "admin":
        raise HTTPException(403, ADMIN_NO_READ)
    if not has_access(request.app.state.settings, user["username"]):
        raise HTTPException(403, NO_ACCESS)
    return user


def page_access(request: Request, render):
    """For HTML routes: (user, None) if allowed, else (None, response to return).

    ``render(status, message)`` builds the refusal page, so each route keeps
    its own layout.
    """
    user = security.authenticate(request)
    if user is None:
        return None, RedirectResponse("/login", status_code=303)
    if user["role"] == "admin":
        return None, render(403, ADMIN_NO_READ, user)
    if not has_access(request.app.state.settings, user["username"]):
        return None, render(403, NO_ACCESS, user)
    return user, None
