from datetime import UTC, datetime, timedelta

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import TokenType, create_token, decode_token, verify_password
from app.models import User, UserRole
from tests.conftest import PASSWORD, auth_headers

REGISTER_PAYLOAD = {
    "organization_name": "Acme Software",
    "full_name": "Ana Admin",
    "email": "Ana@Acme.com",
    "password": "super-secret-123",
}


def test_register_creates_organization_and_admin(client: TestClient, db: Session) -> None:
    response = client.post("/auth/register", json=REGISTER_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == get_settings().access_token_expire_minutes * 60

    user = db.scalar(select(User).where(User.email == "ana@acme.com"))
    assert user is not None
    assert user.role == UserRole.ADMIN
    assert user.organization.name == "Acme Software"


def test_password_is_never_stored_in_plain_text(client: TestClient, db: Session) -> None:
    client.post("/auth/register", json=REGISTER_PAYLOAD)

    user = db.scalar(select(User).where(User.email == "ana@acme.com"))
    assert user is not None
    assert user.hashed_password != REGISTER_PAYLOAD["password"]
    assert user.hashed_password.startswith("$argon2")
    assert verify_password(REGISTER_PAYLOAD["password"], user.hashed_password)


def test_register_rejects_duplicate_email(client: TestClient) -> None:
    client.post("/auth/register", json=REGISTER_PAYLOAD)
    response = client.post("/auth/register", json={**REGISTER_PAYLOAD, "email": "ana@acme.com"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_register_validates_password_length(client: TestClient) -> None:
    response = client.post("/auth/register", json={**REGISTER_PAYLOAD, "password": "short"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["field"] == "body.password"


def test_login_returns_tokens(client: TestClient, agent: User) -> None:
    response = client.post("/auth/login", json={"email": agent.email.upper(), "password": PASSWORD})

    assert response.status_code == 200
    access_token = response.json()["access_token"]
    assert decode_token(access_token, TokenType.ACCESS) == agent.id


def test_login_with_wrong_password_fails(client: TestClient, agent: User) -> None:
    response = client.post("/auth/login", json={"email": agent.email, "password": "wrong-pass"})

    assert response.status_code == 401
    assert response.json() == {
        "error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."}
    }


def test_login_with_unknown_email_fails_the_same_way(client: TestClient) -> None:
    response = client.post("/auth/login", json={"email": "ghost@example.com", "password": PASSWORD})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_inactive_user_cannot_login(client: TestClient, make_user, org) -> None:  # type: ignore[no-untyped-def]
    user = make_user(org, is_active=False)
    response = client.post("/auth/login", json={"email": user.email, "password": PASSWORD})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "USER_INACTIVE"


def test_refresh_issues_new_tokens(client: TestClient, agent: User) -> None:
    refresh_token = create_token(agent.id, TokenType.REFRESH)
    response = client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 200
    assert decode_token(response.json()["access_token"], TokenType.ACCESS) == agent.id


def test_access_token_cannot_be_used_as_refresh_token(client: TestClient, agent: User) -> None:
    access_token = create_token(agent.id, TokenType.ACCESS)
    response = client.post("/auth/refresh", json={"refresh_token": access_token})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_me_returns_current_user(client: TestClient, agent: User) -> None:
    response = client.get("/auth/me", headers=auth_headers(agent))

    assert response.status_code == 200
    assert response.json()["email"] == agent.email
    assert "hashed_password" not in response.json()


def test_me_requires_authentication(client: TestClient) -> None:
    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
    assert response.headers["www-authenticate"] == "Bearer"


def test_expired_token_is_rejected(client: TestClient, agent: User) -> None:
    settings = get_settings()
    past = datetime.now(UTC) - timedelta(hours=2)
    token = jwt.encode(
        {"sub": str(agent.id), "type": "access", "iat": past, "exp": past + timedelta(minutes=5)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "TOKEN_EXPIRED"


def test_token_signed_with_other_key_is_rejected(client: TestClient, agent: User) -> None:
    token = jwt.encode(
        {"sub": str(agent.id), "type": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "an-attacker-controlled-secret-key-with-enough-length",
        algorithm="HS256",
    )
    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"


def test_deactivated_user_token_stops_working(client: TestClient, db: Session, agent: User) -> None:
    headers = auth_headers(agent)
    agent.is_active = False
    db.commit()

    assert client.get("/auth/me", headers=headers).status_code == 401
