from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, categories, priority_rules, teams, tickets, users
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logger import RequestLoggingMiddleware, configure_logging

DESCRIPTION = """
AI-powered service desk that automatically classifies, prioritizes and routes support
tickets while generating context-aware solutions using RAG.

Authenticate with `POST /auth/login`, then click **Authorize** and paste the `access_token`.
"""


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="ResolveAI API", version="0.2.0", description=DESCRIPTION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    register_exception_handlers(app)

    for module in (auth, users, teams, categories, priority_rules, tickets):
        app.include_router(module.router)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
