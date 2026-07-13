"""Read-only API for the preliminary authenticated device monitor."""
from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from .demo_auth import DemoAuth
from .schemas import (
    DemoConnectReq,
    DemoAdviceResp,
    DemoDeviceResp,
    DemoSessionResp,
    DownlinkPayload,
    UplinkPayload,
)


DEMO_SESSION_COOKIE = "sg_demo_session"
ONLINE_WINDOW_SECONDS = 30

router = APIRouter(prefix="/demo/api")


def _auth() -> DemoAuth | None:
    from . import main

    return main._demo_auth


def _bridge() -> Any:
    from . import main

    return main._bridge


def _session_claims(request: Request) -> dict[str, Any]:
    auth = _auth()
    token = request.cookies.get(DEMO_SESSION_COOKIE)
    claims = auth.verify_session(token) if auth is not None and token else None
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    return claims


def _set_session(response: Response, auth: DemoAuth, device_id: str | None) -> None:
    response.set_cookie(
        key=DEMO_SESSION_COOKIE,
        value=auth.issue_session(device_id=device_id),
        max_age=auth.session_ttl_seconds,
        httponly=True,
        samesite="strict",
        secure=auth.secure_cookie,
    )


def _is_online(cache: dict[str, Any], *, now: float | None = None) -> bool:
    received_at = cache.get("received_at")
    if isinstance(received_at, bool) or not isinstance(received_at, (int, float)):
        return False
    age = (time.time() if now is None else now) - received_at
    return 0 <= age <= ONLINE_WINDOW_SECONDS


def _cache_for_device(device_id: str) -> dict[str, Any] | None:
    bridge = _bridge()
    if bridge is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="monitor unavailable")
    cache = bridge.cache_snapshot(device_id)
    return cache if isinstance(cache, dict) else None


@router.post("/login", response_model=DemoSessionResp)
async def login(request: Request, response: Response) -> DemoSessionResp:
    try:
        body = await request.json()
    except (UnicodeDecodeError, ValueError):
        body = None
    username = body.get("username") if isinstance(body, dict) else None
    password = body.get("password") if isinstance(body, dict) else None
    auth = _auth()
    if not isinstance(username, str) or not isinstance(password, str) or auth is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")
    if not auth.verify_login(username, password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password")
    _set_session(response, auth, device_id=None)
    return DemoSessionResp(authenticated=True)


@router.post("/logout", response_model=DemoSessionResp)
async def logout(request: Request, response: Response) -> DemoSessionResp:
    _session_claims(request)
    auth = _auth()
    response.delete_cookie(
        key=DEMO_SESSION_COOKIE,
        httponly=True,
        samesite="strict",
        secure=auth.secure_cookie if auth is not None else True,
    )
    return DemoSessionResp(authenticated=False)


@router.get("/session", response_model=DemoSessionResp)
async def session(request: Request) -> DemoSessionResp:
    claims = _session_claims(request)
    return DemoSessionResp(authenticated=True, device_id=claims.get("device_id"))


@router.post("/connect", response_model=DemoSessionResp)
async def connect(request: Request, response: Response, req: DemoConnectReq) -> DemoSessionResp:
    _session_claims(request)
    cache = _cache_for_device(req.device_id)
    if cache is None or not isinstance(cache.get("uplink"), UplinkPayload):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="device not found")
    if not _is_online(cache):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="device is offline")
    auth = _auth()
    if auth is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    _set_session(response, auth, device_id=req.device_id)
    return DemoSessionResp(authenticated=True, device_id=req.device_id)


@router.post("/disconnect", response_model=DemoSessionResp)
async def disconnect(request: Request, response: Response) -> DemoSessionResp:
    _session_claims(request)
    auth = _auth()
    if auth is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    _set_session(response, auth, device_id=None)
    return DemoSessionResp(authenticated=True)


@router.get("/device", response_model=DemoDeviceResp)
async def device(request: Request) -> DemoDeviceResp:
    claims = _session_claims(request)
    device_id = claims.get("device_id")
    if device_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="device not connected")

    cache = _cache_for_device(device_id)
    if cache is None:
        return DemoDeviceResp(device_id=device_id, online=False)
    uplink = cache.get("uplink")
    advice = cache.get("advice")
    if not isinstance(uplink, UplinkPayload):
        return DemoDeviceResp(
            device_id=device_id,
            online=False,
            received_at=cache.get("received_at"),
        )
    demo_advice = None
    if isinstance(advice, DownlinkPayload):
        demo_advice = DemoAdviceResp(
            advice_text=advice.advice_text,
            source=advice.source,
            ts=advice.ts,
        )
    return DemoDeviceResp(
        device_id=device_id,
        online=_is_online(cache),
        received_at=cache.get("received_at"),
        scores=uplink.scores,
        level=uplink.level,
        reasons=uplink.reasons,
        veto_by=uplink.veto_by,
        advice=demo_advice,
    )
