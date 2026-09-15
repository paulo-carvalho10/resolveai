from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.schemas.common import NormalizedEmail, Password

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]


class RegisterRequest(BaseModel):
    """Signs up a new organization together with its first administrator."""

    organization_name: FullName
    full_name: FullName
    email: NormalizedEmail
    password: Password


class LoginRequest(BaseModel):
    email: NormalizedEmail
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
