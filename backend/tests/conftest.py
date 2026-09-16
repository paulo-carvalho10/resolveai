"""Test fixtures.

Tests run on an in-memory SQLite database by default. Set TEST_DATABASE_URL to run them
against PostgreSQL (CI does this).
"""

import os

os.environ["ENVIRONMENT"] = "test"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-long-enough-for-hs256-signing"
# Safety net: anything that bypasses the fixtures below must never reach a real database or
# the paid AI API, even if a local .env points at them.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["AI_PROVIDER"] = "keyword"
os.environ["EMBEDDING_PROVIDER"] = "local"
# The auto-close job would close tickets a test just created; tests that need it turn it on.
os.environ["AUTO_CLOSE_INTERVAL_MINUTES"] = "0"
os.environ.pop("ANTHROPIC_API_KEY", None)
os.environ.pop("VOYAGE_API_KEY", None)

from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import (
    get_answer_generator,
    get_classifier,
    get_embedder,
    get_session_factory,
)
from app.core.database import get_db
from app.core.security import TokenType, create_token, hash_password
from app.main import app
from app.models import Base, Organization, User, UserRole
from app.services.ai_classifier import Classifier, KeywordClassifier
from app.services.answer_generator import AnswerGenerator, ExtractiveAnswerGenerator
from app.services.embeddings import Embedder, HashingEmbedder

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "sqlite+pysqlite:///:memory:")
PASSWORD = "correct-horse-battery"


@pytest.fixture
def engine() -> Iterator[Engine]:
    if TEST_DATABASE_URL.startswith("sqlite"):
        engine = create_engine(
            TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _):  # type: ignore[no-untyped-def]
            dbapi_connection.execute("PRAGMA foreign_keys=ON")
    else:
        engine = create_engine(TEST_DATABASE_URL)
        # The schema comes from metadata, not migrations, so enable pgvector here.
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture
def classifier() -> Classifier:
    """Override in a test module to control what the AI returns."""
    return KeywordClassifier()


@pytest.fixture
def embedder() -> Embedder:
    return HashingEmbedder()


@pytest.fixture
def answer_generator() -> AnswerGenerator:
    return ExtractiveAnswerGenerator()


@pytest.fixture
def client(
    session_factory: sessionmaker[Session],
    classifier: Classifier,
    embedder: Embedder,
    answer_generator: AnswerGenerator,
) -> Iterator[TestClient]:
    def override_get_db() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    # Background AI analysis opens its own session: it must use the test database too.
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_classifier] = lambda: classifier
    app.dependency_overrides[get_embedder] = lambda: embedder
    app.dependency_overrides[get_answer_generator] = lambda: answer_generator
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --- Data factories ------------------------------------------------------------------------


@pytest.fixture
def make_org(db: Session) -> Callable[..., Organization]:
    def factory(name: str = "Acme") -> Organization:
        org = Organization(name=name)
        db.add(org)
        db.commit()
        return org

    return factory


@pytest.fixture
def make_user(db: Session) -> Callable[..., User]:
    counter = iter(range(1, 10_000))

    def factory(
        organization: Organization,
        role: UserRole = UserRole.USER,
        email: str | None = None,
        full_name: str | None = None,
        is_active: bool = True,
    ) -> User:
        n = next(counter)
        user = User(
            organization_id=organization.id,
            email=email or f"{role.lower()}{n}@example.com",
            full_name=full_name or f"{role.title()} {n}",
            hashed_password=hash_password(PASSWORD),
            role=role,
            is_active=is_active,
        )
        db.add(user)
        db.commit()
        return user

    return factory


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_token(user.id, TokenType.ACCESS)}"}


@pytest.fixture
def org(make_org: Callable[..., Organization]) -> Organization:
    return make_org("Acme Software")


@pytest.fixture
def other_org(make_org: Callable[..., Organization]) -> Organization:
    return make_org("Globex")


@pytest.fixture
def admin(make_user: Callable[..., User], org: Organization) -> User:
    return make_user(org, UserRole.ADMIN, full_name="Ana Admin")


@pytest.fixture
def agent(make_user: Callable[..., User], org: Organization) -> User:
    return make_user(org, UserRole.AGENT, full_name="Maria Agent")


@pytest.fixture
def requester(make_user: Callable[..., User], org: Organization) -> User:
    return make_user(org, UserRole.USER, full_name="Joao User")


@pytest.fixture
def other_admin(make_user: Callable[..., User], other_org: Organization) -> User:
    return make_user(other_org, UserRole.ADMIN, full_name="Other Admin")
