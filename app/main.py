"""Throughline: the App Studio account base plus transcript retrieval for therapists."""

from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app import branding, database, security
from app import care
from app.features import accounts, ask, roles
from app.rag.store import Index
from app.settings import Settings

APP_ROOT = Path(__file__).resolve().parent


def create_app(settings=None, embedder=None, import_vectors=True):
    """Create an isolated testable app; no test uses real runtime data."""
    settings = settings or Settings.load()
    database.initialize(settings)
    with database.connect(settings) as connection:
        connection.executescript(care.SCHEMA)
    rag = Index(settings.rag_dir, embedder=embedder)
    rag.import_directory(settings.corpus, vectors=import_vectors)
    # Uploaded versions win over the bundled ones, so a restart keeps them.
    uploaded = settings.rag_dir.parent / "uploads"
    if uploaded.is_dir():
        rag.import_directory(uploaded, vectors=import_vectors)
    application = FastAPI(title="Throughline", docs_url=None, redoc_url=None)
    application.state.rag = rag
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[urlsplit(settings.origin).hostname],
        www_redirect=False,
    )
    application.state.settings = settings
    application.state.current_user = security.authenticate
    application.state.brand = branding.load_brand
    application.state.templates = Jinja2Templates(directory=APP_ROOT / "templates")
    application.include_router(accounts.router)
    application.include_router(roles.router)
    application.include_router(ask.router)
    application.state.feature_flags = lambda: {
        "accounts": any(route.path == "/api/me" for route in accounts.router.routes),
        "roles": any(route.path == "/api/admin" for route in roles.router.routes),
    }
    application.mount(
        "/static", StaticFiles(directory=APP_ROOT / "static"), name="static"
    )

    @application.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        # FastAPI's default error can echo rejected input, including passwords.
        details = [
            {key: item[key] for key in ("loc", "msg", "type")}
            for item in error.errors()
        ]
        return JSONResponse({"detail": details}, status_code=422)

    @application.middleware("http")
    async def response_protections(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; connect-src 'self'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        if not request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store"
        if settings.mode == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response

    @application.get("/", include_in_schema=False)
    def home(request: Request):
        return application.state.templates.TemplateResponse(
            request=request, name="home.html", context={}
        )

    @application.get("/docs", include_in_schema=False)
    def api_map(request: Request):
        return application.state.templates.TemplateResponse(
            request=request, name="api.html", context={}
        )

    @application.get("/health")
    def health():
        return {"status": "ok", "mode": settings.mode}

    @application.get("/brand.css", include_in_schema=False)
    def brand_css():
        return Response(branding.stylesheet(), media_type="text/css")

    return application
