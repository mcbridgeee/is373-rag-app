"""Ask, read and upload a client's sessions: therapists on the client's care team only.

Admins are refused here on purpose: they manage access, not records.
"""

from typing import Annotated, Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from pydantic import BaseModel, ConfigDict, Field

from app import care, security
from app.features.accounts import _page
from app.private_files import private_directory, private_file
from app.rag import answer as answering
from app.rag.corpus import parse

router = APIRouter()
FormText = Annotated[str, Form()]
MAX_QUESTION = 300
MAX_UPLOAD_BYTES = 200_000
TOP_K = 5


class AskInput(BaseModel):
    """A question and which retriever to use. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=3, max_length=MAX_QUESTION)
    method: Literal["vector", "keyword"] = "vector"


def _refusal(request):
    """The page shown to admins and to therapists without access."""

    def render(status, message, user):
        return _page(request, "refused.html", status, user=user, message=message)

    return render


def _run(request: Request, question: str, method: str) -> answering.Answer:
    index = request.app.state.rag
    hits = index.retrieve(question.strip(), method=method, k=TOP_K)
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
    _user: Annotated[dict, Depends(care.require_care)],
    x_csrf_token: Annotated[str | None, Header()] = None,
):
    """401 before login, 403 for admins and for therapists without access."""
    security.require_csrf(request, x_csrf_token)
    return _as_json(_run(request, payload.question, payload.method))


@router.get("/ask", include_in_schema=False)
def ask_page(request: Request):
    user, refused = care.page_access(request, _refusal(request))
    if refused:
        return refused
    return _page(request, "ask.html", user=user, method="vector", client=care.CLIENT)


@router.post("/ask", include_in_schema=False)
def ask_submit(
    request: Request,
    question: FormText = "",
    method: FormText = "vector",
    csrf_token: FormText = "",
):
    user, refused = care.page_access(request, _refusal(request))
    if refused:
        return refused
    try:
        security.require_csrf(request, csrf_token)
        payload = AskInput(question=question, method=method)
    except HTTPException as error:
        return _page(
            request,
            "ask.html",
            error.status_code,
            user=user,
            client=care.CLIENT,
            error=error.detail,
        )
    except ValueError:
        return _page(
            request,
            "ask.html",
            422,
            user=user,
            client=care.CLIENT,
            method="vector",
            error=f"Ask a question between 3 and {MAX_QUESTION} characters.",
        )
    result = _run(request, payload.question, payload.method)
    return _page(
        request,
        "ask.html",
        user=user,
        client=care.CLIENT,
        question=payload.question,
        method=payload.method,
        result=result,
        segments=answering.segments(result.text),
        cited=set(result.cited),
    )


@router.get("/sessions", include_in_schema=False)
def sessions_page(request: Request):
    user, refused = care.page_access(request, _refusal(request))
    if refused:
        return refused
    return _page(
        request,
        "sessions.html",
        user=user,
        client=care.CLIENT,
        sessions=request.app.state.rag.sessions(),
    )


@router.get("/sessions/{session_id}", include_in_schema=False)
def session_page(request: Request, session_id: str):
    user, refused = care.page_access(request, _refusal(request))
    if refused:
        return refused
    found = request.app.state.rag.session(session_id)
    if found is None:
        raise HTTPException(404, "No such session.")
    document, chunks = found
    return _page(request, "session.html", user=user, document=document, chunks=chunks)


# ---- upload --------------------------------------------------------------


def uploads_dir(settings):
    """Uploaded transcripts live beside the indexes, in the private data volume."""
    path = settings.rag_dir.parent / "uploads"
    private_directory(path)
    return path


async def _read_upload(upload: UploadFile) -> str:
    """Check the file before anything is stored. Raises ValueError with a reason."""
    if not (upload.filename or "").lower().endswith(".md"):
        raise ValueError("Upload a Markdown (.md) transcript file.")
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("That file is over 200 KB. Upload one session at a time.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("The file must be UTF-8 text.") from None


@router.get("/upload", include_in_schema=False)
def upload_page(request: Request):
    user, refused = care.page_access(request, _refusal(request))
    if refused:
        return refused
    return _page(request, "upload.html", user=user, client=care.CLIENT)


@router.post("/upload", include_in_schema=False)
async def upload_submit(
    request: Request,
    transcript: Annotated[UploadFile, File()],
    csrf_token: FormText = "",
):
    user, refused = care.page_access(request, _refusal(request))
    if refused:
        return refused
    try:
        security.require_csrf(request, csrf_token)
        text = await _read_upload(transcript)
        session = parse(text)
    except HTTPException as error:
        return _page(
            request,
            "upload.html",
            error.status_code,
            user=user,
            client=care.CLIENT,
            error=error.detail,
        )
    except ValueError as error:
        return _page(
            request, "upload.html", 422, user=user, client=care.CLIENT, error=str(error)
        )
    settings = request.app.state.settings
    status = request.app.state.rag.import_transcript(session)
    # Keep the file so a restart re-imports the same version (see main.py).
    saved = uploads_dir(settings) / f"{session.id}.md"
    saved.write_text(text, encoding="utf-8")
    private_file(saved)
    messages = {
        "added": f"Added {session.id}. It is now searchable.",
        "updated": f"Replaced {session.id} with this version; its old passages were removed.",
        "unchanged": f"{session.id} is already imported with identical text. Nothing changed.",
    }
    return _page(
        request,
        "upload.html",
        user=user,
        client=care.CLIENT,
        notice=messages[status],
        session_id=session.id,
    )
