"""Ask questions across a client's sessions. Logged-in users only, pages and API alike."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from app import security
from app.features.accounts import _page
from app.rag import answer as answering

router = APIRouter()
FormText = Annotated[str, Form()]
MAX_QUESTION = 300


class AskInput(BaseModel):
    """A question and which retriever to use. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=MAX_QUESTION)
    method: Literal["vector", "keyword"] = "vector"


def _run(request: Request, question: str, method: str) -> answering.Answer:
    index = request.app.state.rag
    hits = index.retrieve(question.strip(), method=method, k=5)
    return answering.answer(question.strip(), hits)


def _as_json(result: answering.Answer) -> dict:
    return {
        "answer": result.text,
        "generated": result.generated,
        "cited": result.cited,
        "warnings": result.warnings,
        "passages": [
            {
                "id": hit.chunk.id,
                "session": hit.chunk.session_id,
                "date": hit.chunk.session_date,
                "start": hit.chunk.start,
                "score": round(hit.score, 4),
                "url": f"/sessions/{hit.chunk.session_id}#{hit.chunk.id}",
                "text": hit.chunk.text,
            }
            for hit in result.hits
        ],
    }


@router.post("/api/ask")
def api_ask(
    request: Request,
    payload: AskInput,
    _user: Annotated[dict, Depends(security.require_user)],
    x_csrf_token: Annotated[str | None, Header()] = None,
):
    """401 before login. Answers cite chunk IDs that link to the session page."""
    security.require_csrf(request, x_csrf_token)
    return _as_json(_run(request, payload.question, payload.method))


@router.get("/ask", include_in_schema=False)
def ask_page(request: Request):
    user = security.authenticate(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _page(request, "ask.html", user=user, method="vector")


@router.post("/ask", include_in_schema=False)
def ask_submit(
    request: Request,
    question: FormText = "",
    method: FormText = "vector",
    csrf_token: FormText = "",
):
    user = security.authenticate(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    try:
        security.require_csrf(request, csrf_token)
        payload = AskInput(question=question, method=method)
    except HTTPException as error:
        return _page(
            request, "ask.html", error.status_code, user=user, error=error.detail
        )
    except ValueError:
        return _page(
            request,
            "ask.html",
            422,
            user=user,
            method="vector",
            error=f"Ask a question between 3 and {MAX_QUESTION} characters.",
        )
    result = _run(request, payload.question, payload.method)
    return _page(
        request,
        "ask.html",
        user=user,
        question=payload.question,
        method=payload.method,
        result=result,
        segments=answering.segments(result.text),
        cited=set(result.cited),
    )


@router.get("/sessions", include_in_schema=False)
def sessions_page(request: Request):
    user = security.authenticate(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    return _page(
        request, "sessions.html", user=user, sessions=request.app.state.rag.sessions()
    )


@router.get("/sessions/{session_id}", include_in_schema=False)
def session_page(request: Request, session_id: str):
    user = security.authenticate(request)
    if user is None:
        return RedirectResponse("/login", status_code=303)
    found = request.app.state.rag.session(session_id)
    if found is None:
        raise HTTPException(404, "No such session.")
    document, chunks = found
    return _page(request, "session.html", user=user, document=document, chunks=chunks)
