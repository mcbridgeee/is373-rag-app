"""Admins manage who can see a client's transcripts; they never see the transcripts.

The server checks the current database role on every request, so a downgraded
admin loses this page immediately.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict

from app import care, security
from app.database import connect
from app.features.accounts import _page

router = APIRouter()
FormText = Annotated[str, Form()]


class AccessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    action: Literal["grant", "remove"]


def _accounts(settings):
    """Usernames, roles and access; never ids, hashes or sessions."""
    with connect(settings) as connection:
        rows = connection.execute(
            "SELECT username, role FROM users ORDER BY username"
        ).fetchall()
    members = care.team(settings)
    return [
        {
            "username": row["username"],
            "role": "therapist" if row["role"] == "member" else row["role"],
            "access": row["username"] in members,
        }
        for row in rows
    ]


def _apply(settings, admin, payload: AccessInput) -> str:
    try:
        changed = care.change(
            settings, admin["username"], payload.username, payload.action == "grant"
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    name = payload.username.strip().lower()
    if not changed:
        return f"No change: {name} already {'has' if payload.action == 'grant' else 'lacks'} access."
    verb = "can now see" if payload.action == "grant" else "can no longer see"
    return f"{name} {verb} {care.CLIENT['label']}'s transcripts."


@router.get("/api/admin")
def api_admin(
    request: Request, _admin: Annotated[dict, Depends(security.require_admin)]
):
    """Anonymous → 401, therapist → 403, admin → 200 with accounts and the access log."""
    settings = request.app.state.settings
    return {"accounts": _accounts(settings), "access_log": care.history(settings)}


@router.post("/api/admin/access")
def api_access(
    request: Request,
    payload: AccessInput,
    admin: Annotated[dict, Depends(security.require_admin)],
    x_csrf_token: Annotated[str | None, Header()] = None,
):
    security.require_csrf(request, x_csrf_token)
    return {"message": _apply(request.app.state.settings, admin, payload)}


def _admin_page(request, status=200, **context):
    settings = request.app.state.settings
    return _page(
        request,
        "admin.html",
        status,
        denied=False,
        client=care.CLIENT,
        accounts=_accounts(settings),
        log=care.history(settings),
        **context,
    )


@router.get("/admin", include_in_schema=False)
def admin_page(request: Request):
    """The same boundary for a typed URL: hiding the nav link is not the check."""
    user = security.authenticate(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        return _page(request, "admin.html", 403, denied=True)
    return _admin_page(request)


@router.post("/admin/access", include_in_schema=False)
def admin_access(
    request: Request,
    username: FormText = "",
    action: FormText = "",
    csrf_token: FormText = "",
):
    user = security.authenticate(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    if user["role"] != "admin":
        return _page(request, "admin.html", 403, denied=True)
    try:
        security.require_csrf(request, csrf_token)
        message = _apply(
            request.app.state.settings,
            user,
            AccessInput(username=username, action=action),
        )
    except HTTPException as error:
        return _admin_page(request, error.status_code, error=error.detail)
    except ValueError:
        return _admin_page(request, 422, error="Choose grant or remove for an account.")
    return _admin_page(request, notice=message)
