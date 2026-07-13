from __future__ import annotations

import os
import sqlite3
import time
from collections import defaultdict, deque
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

router = APIRouter()


class LoginRateLimiter:
    def __init__(self) -> None:
        self._failures: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def check(self, ip_address: str, username: str) -> None:
        failures = self._recent_failures(ip_address, username)
        if len(failures) >= MAX_LOGIN_FAILURES:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts")

    def record_failure(self, ip_address: str, username: str) -> None:
        self._recent_failures(ip_address, username).append(time.monotonic())

    def clear(self, ip_address: str, username: str) -> None:
        self._failures.pop((ip_address, username), None)

    def _recent_failures(self, ip_address: str, username: str) -> deque[float]:
        key = (ip_address, username)
        failures = self._failures[key]
        cutoff = time.monotonic() - LOGIN_FAILURE_WINDOW_SECONDS
        while failures and failures[0] <= cutoff:
            failures.popleft()
        return failures


def bootstrap_auth_store() -> AuthStore:
    db_path = Path(_required_env("SG_AUTH_DB"))
    pairing_secret = _required_env("SG_PAIRING_SECRET").encode("utf-8")
    store = AuthStore(db_path, pairing_secret=pairing_secret)
    store.initialize()
    if not store.list_users():
        username = _required_env("SG_INITIAL_ADMIN_USER")
        password = _required_env("SG_INITIAL_ADMIN_PASSWORD")
        try:
            store.create_user(username, hash_password(password), "admin")
        finally:
            os.environ.pop("SG_INITIAL_ADMIN_PASSWORD", None)
    else:
        os.environ.pop("SG_INITIAL_ADMIN_PASSWORD", None)
    return store


def get_current_user(
    request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> UserRecord:
    token = _session_token(authorization, session_cookie)
    if token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        user = request.app.state.auth_store.authenticate_session(token)
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
    limiter.check(ip_address, username)
    try:
        user = request.app.state.auth_store.verify_login(payload.username, payload.password)
    except ValueError:
        user = None
    if user is None:
        limiter.record_failure(ip_address, username)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, AUTH_FAILURE_DETAIL)
    limiter.clear(ip_address, username)
    token = request.app.state.auth_store.create_session(
        user.id, expires_at=int(time.time()) + SESSION_TTL_SECONDS
    )
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
    response: Response,
    request: Request,
    authorization: str | None = Header(default=None),
    session_cookie: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    token = _session_token(authorization, session_cookie)
    if token is not None:
        try:
            request.app.state.auth_store.revoke_session(token)
        except ValueError:
            pass
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
    except (sqlite3.IntegrityError, ValueError):
        raise HTTPException(status.HTTP_409_CONFLICT, "Username is unavailable") from None
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
        raise RuntimeError(f"{name} is required")
    return value


def _normalized_username(username: str) -> str:
    return username.strip().casefold() if isinstance(username, str) else ""


def _session_token(authorization: str | None, session_cookie: str | None) -> str | None:
    if authorization is not None:
        scheme, _, token = authorization.partition(" ")
        return token if scheme.casefold() == "bearer" and token else None
    return session_cookie


def _public_user(user: UserRecord) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
        is_active=user.is_active,
    )
