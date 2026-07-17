"""Read-only API for the preliminary authenticated device monitor."""
from __future__ import annotations

import asyncio
import threading
import time
from collections import OrderedDict, deque
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket, WebSocketDisconnect, status

from .demo_auth import DemoAuth
from .schemas import (
    DemoConnectReq,
    DemoAdviceResp,
    DemoDeviceResp,
    DemoSessionResp,
    DemoScreeningReq,
    DemoScreeningResp,
    DownlinkPayload,
    UplinkPayload,
)


DEMO_SESSION_COOKIE = "sg_demo_session"
ONLINE_WINDOW_SECONDS = 30
ADVICE_VISIBLE_SECONDS = 300
LOGIN_WINDOW_SECONDS = 60
LOGIN_MAX_ATTEMPTS = 5
LOGIN_MAX_CLIENTS = 1024


class _LoginLimiter:
    """Small process-local limiter for the single-account preliminary demo."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, client_id: str) -> bool:
        now = self._clock()
        cutoff = now - LOGIN_WINDOW_SECONDS
        with self._lock:
            attempts = self._attempts.setdefault(client_id, deque())
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= LOGIN_MAX_ATTEMPTS:
                self._attempts.move_to_end(client_id)
                return False
            attempts.append(now)
            self._attempts.move_to_end(client_id)
            while len(self._attempts) > LOGIN_MAX_CLIENTS:
                self._attempts.popitem(last=False)
            return True


_login_limiter = _LoginLimiter()
_login_verify_slots = asyncio.Semaphore(2)

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


def _claims_from_token(token: str | None) -> dict[str, Any] | None:
    auth = _auth()
    return auth.verify_session(token) if auth is not None and token else None


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


def _visible_advice(
    cache: dict[str, Any], *, now: float | None = None
) -> DownlinkPayload | None:
    advice = cache.get("advice")
    if not isinstance(advice, DownlinkPayload):
        return None
    age = (time.time() if now is None else now) - advice.ts
    return advice if 0 <= age <= ADVICE_VISIBLE_SECONDS else None


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
    client_id = request.client.host if request.client is not None else "unknown"
    if not _login_limiter.allow(client_id):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="too many login attempts")
    async with _login_verify_slots:
        verified = await asyncio.to_thread(auth.verify_login, username, password)
    if not verified:
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


@router.post("/screening", response_model=DemoScreeningResp)
async def screening(request: Request, req: DemoScreeningReq) -> DemoScreeningResp:
    claims = _session_claims(request)
    device_id = claims.get("device_id")
    if not isinstance(device_id, str):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="device not connected")
    cache = _cache_for_device(device_id)
    if cache is None or not _is_online(cache):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="device is offline")
    bridge = _bridge()
    if bridge is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="control unavailable")
    if req.action == "start":
        bridge.invalidate_advice(device_id)
    if not bridge.publish_screening_control(device_id, req.action):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="control unavailable")
    return DemoScreeningResp(accepted=True, action=req.action)


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
    advice = _visible_advice(cache)
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
        screening_stage=uplink.screening_stage,
    )


@router.websocket("/ws")
async def device_ws(websocket: WebSocket) -> None:
    claims = _claims_from_token(websocket.cookies.get(DEMO_SESSION_COOKIE))
    device_id = claims.get("device_id") if claims else None
    if not isinstance(device_id, str):
        await websocket.close(code=4401)
        return
    await websocket.accept()
    last_marker: tuple[Any, Any] | None = None
    try:
        while True:
            if _claims_from_token(websocket.cookies.get(DEMO_SESSION_COOKIE)) is None:
                await websocket.close(code=4401)
                return
            cache = _cache_for_device(device_id)
            advice = _visible_advice(cache) if cache else None
            marker = (
                cache.get("generation") if cache else None,
                cache.get("received_at") if cache else None,
                advice.ts if advice else None,
            )
            if marker != last_marker:
                uplink = cache.get("uplink") if cache else None
                payload = DemoDeviceResp(
                    device_id=device_id,
                    online=bool(cache and _is_online(cache)),
                    received_at=cache.get("received_at") if cache else None,
                    scores=uplink.scores if isinstance(uplink, UplinkPayload) else None,
                    level=uplink.level if isinstance(uplink, UplinkPayload) else None,
                    reasons=uplink.reasons if isinstance(uplink, UplinkPayload) else [],
                    veto_by=uplink.veto_by if isinstance(uplink, UplinkPayload) else [],
                    advice=DemoAdviceResp(
                        advice_text=advice.advice_text, source=advice.source, ts=advice.ts
                    ) if isinstance(advice, DownlinkPayload) else None,
                    screening_stage=uplink.screening_stage if isinstance(uplink, UplinkPayload) else 0,
                )
                await websocket.send_json(payload.model_dump(mode="json"))
                last_marker = marker
            await asyncio.sleep(0.25)
    except WebSocketDisconnect:
        return
