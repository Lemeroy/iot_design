from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status

from .auth_store import AuthStore, UserRecord
from .schemas import (
    LoginRequest,
    LoginResponse,
    UserActivationUpdate,
    UserCreateRequest,
    UserResponse,
)
from .security import hash_password


SESSION_COOKIE = "sg_session"
SESSION_TTL_SECONDS = 8 * 60 * 60
AUTH_FAILURE_DETAIL = "\u8d26\u53f7\u6216\u5bc6\u7801\u9519\u8bef"
MAX_LOGIN_FAILURES = 5
LOGIN_FAILURE_WINDOW_SECONDS = 5 * 60


class AuthConfigurationError(ValueError):
    pass


def require_auth_available(request: Request) -> None:
    if not getattr(request.app.state, "auth_enabled", False):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication is unavailable")


router = APIRouter(dependencies=[Depends(require_auth_available)])


@dataclass(frozen=True)
class LoginAttempt:
    key: tuple[str, str]
    identifier: int


class LoginRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
        self._lock = threading.Lock()
        self._next_identifier = 0

    def begin_attempt(self, ip_address: str, username: str) -> LoginAttempt:
        key = (ip_address, username)
        with self._lock:
            attempts = self._recent_attempts(key)
            if len(attempts) >= MAX_LOGIN_FAILURES:
                raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts")
            self._next_identifier += 1
            identifier = self._next_identifier
            attempts[identifier] = time.monotonic()
        return LoginAttempt(key, identifier)

    def complete_attempt(self, attempt: LoginAttempt, *, failed: bool) -> None:
        if failed:
            return
        with self._lock:
            attempts = self._attempts.get(attempt.key)
            if attempts is not None:
                attempts.pop(attempt.identifier, None)
                if not attempts:
                    self._attempts.pop(attempt.key, None)

    def _recent_attempts(self, key: tuple[str, str]) -> dict[int, float]:
        attempts = self._attempts[key]
        cutoff = time.monotonic() - LOGIN_FAILURE_WINDOW_SECONDS
        for identifier, timestamp in tuple(attempts.items()):
            if timestamp <= cutoff:
                del attempts[identifier]
        return attempts


def bootstrap_auth_store() -> AuthStore | None:
    try:
        db_path = Path(_required_env("SG_AUTH_DB"))
        pairing_secret = _required_env("SG_PAIRING_SECRET").encode("utf-8")
        store = AuthStore(db_path, pairing_secret=pairing_secret)
        store.initialize()
        if not store.list_users():
            username = _required_env("SG_INITIAL_ADMIN_USER")
            password = _required_env("SG_INITIAL_ADMIN_PASSWORD")
            store.create_user(username, hash_password(password), "admin")
        return store
    except AuthConfigurationError:
        return None
    finally:
        os.environ.pop("SG_INITIAL_ADMIN_PASSWORD", None)


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> UserRecord:
    token, client_type = _session_credentials(authorization, session_cookie)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        user = request.app.state.auth_store.authenticate_session(token, client_type=client_type)
    except ValueError:
        user = None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    return user


def require_admin(current_user: Annotated[UserRecord, Depends(get_current_user)]) -> UserRecord:
    if current_user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Administrator access required")
    return current_user


@router.post("/api/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest, response: Response, request: Request) -> LoginResponse:
    ip_address = request.client.host if request.client else "unknown"
    username = _normalized_username(payload.username)
    limiter: LoginRateLimiter = request.app.state.auth_limiter
    attempt = limiter.begin_attempt(ip_address, username)
    try:
        user = request.app.state.auth_store.verify_login(payload.username, payload.password)
    except ValueError:
        user = None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, AUTH_FAILURE_DETAIL)
    limiter.complete_attempt(attempt, failed=False)
    token = request.app.state.auth_store.create_session(
        user.id, expires_at=int(time.time()) + SESSION_TTL_SECONDS, client_type=payload.client
    )
    if payload.client == "browser":
        response.set_cookie(
            SESSION_COOKIE,
            token,
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=SESSION_TTL_SECONDS,
        )
    return LoginResponse(user=_public_user(user), access_token=token if payload.client == "pc" else None)


@router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    token, _ = _session_credentials(authorization, session_cookie)
    if token is not None:
        try:
            request.app.state.auth_store.revoke_session(token)
        except ValueError:
            pass
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(SESSION_COOKIE, httponly=True, secure=True, samesite="strict")
    return response


@router.get("/api/auth/me", response_model=UserResponse)
def current_user(current_user: Annotated[UserRecord, Depends(get_current_user)]) -> UserResponse:
    return _public_user(current_user)


@router.post("/api/admin/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreateRequest,
    request: Request,
    _: Annotated[UserRecord, Depends(require_admin)],
) -> UserResponse:
    try:
        user = request.app.state.auth_store.create_user(
            payload.username, hash_password(payload.password), "user"
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status.HTTP_409_CONFLICT, "Username is unavailable") from None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid user input") from None
    return _public_user(user)


@router.get("/api/admin/users", response_model=list[UserResponse])
def list_users(
    request: Request, _: Annotated[UserRecord, Depends(require_admin)]
) -> list[UserResponse]:
    return [_public_user(user) for user in request.app.state.auth_store.list_users()]


@router.patch("/api/admin/users/{user_id}", response_model=UserResponse)
def set_user_active(
    user_id: int,
    payload: UserActivationUpdate,
    request: Request,
    _: Annotated[UserRecord, Depends(require_admin)],
) -> UserResponse:
    user = request.app.state.auth_store.set_user_active(user_id, payload.is_active)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _public_user(user)


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise AuthConfigurationError(f"{name} is required")
    return value


def _normalized_username(username: str) -> str:
    return username.strip().casefold() if isinstance(username, str) else ""


def _session_credentials(
    authorization: str | None, session_cookie: str | None
) -> tuple[str | None, str]:
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        return (token, "pc") if scheme.casefold() == "bearer" and token else (None, "pc")
    return session_cookie, "browser"


def _public_user(user: UserRecord) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
    )
