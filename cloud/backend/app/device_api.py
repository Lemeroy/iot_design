from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from .auth_api import get_current_user, require_admin, require_auth_available
from .auth_store import DeviceRecord, PairingError, UserRecord
from .schemas import (
    AdminDeviceResponse,
    DeviceResponse,
    LatestResp,
    PairDeviceRequest,
    PairingCodeResponse,
)


DEVICE_NOT_FOUND_DETAIL = "\u8bbe\u5907\u4e0d\u5b58\u5728"
PAIRING_ERROR_DETAIL = "\u7ed1\u5b9a\u7801\u65e0\u6548\u6216\u5df2\u8fc7\u671f"

router = APIRouter(dependencies=[Depends(require_auth_available)])


def require_device_access(request: Request, device_id: str, user: UserRecord) -> DeviceRecord:
    device = request.app.state.auth_store.get_device(device_id)
    if device is None or (user.role != "admin" and device.owner_user_id != user.id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, DEVICE_NOT_FOUND_DETAIL)
    return device


@router.get("/api/devices", response_model=list[DeviceResponse])
def list_devices(
    request: Request, current_user: Annotated[UserRecord, Depends(get_current_user)]
) -> list[DeviceResponse]:
    owner_user_id = None if current_user.role == "admin" else current_user.id
    return [_device_response(device) for device in request.app.state.auth_store.list_devices(
        owner_user_id=owner_user_id
    )]


@router.get("/api/devices/{device_id}/latest", response_model=LatestResp)
def latest(
    device_id: str,
    request: Request,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> LatestResp:
    device = require_device_access(request, device_id, current_user)
    bridge = getattr(request.app.state, "bridge", None)
    if bridge is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "bridge not ready")
    cache = bridge.latest.get(device.device_id)
    if not cache:
        return LatestResp(device_id=device.device_id)
    uplink = cache.get("uplink")
    advice = cache.get("advice")
    return LatestResp(
        device_id=device.device_id,
        last_uplink_ts=uplink.ts if uplink else None,
        last_advice=advice,
        latest_scores=uplink.scores if uplink else None,
        latest_level=uplink.level if uplink else None,
    )


@router.post("/api/devices/pair", response_model=DeviceResponse)
def pair_device(
    payload: PairDeviceRequest,
    request: Request,
    current_user: Annotated[UserRecord, Depends(get_current_user)],
) -> DeviceResponse:
    try:
        device_id = request.app.state.auth_store.consume_pairing_code(payload.code, current_user.id)
    except (PairingError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, PAIRING_ERROR_DETAIL) from None
    device = request.app.state.auth_store.get_device(device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DEVICE_NOT_FOUND_DETAIL)
    return _device_response(device)


@router.get("/api/admin/devices", response_model=list[AdminDeviceResponse])
def list_all_devices(
    request: Request, _: Annotated[UserRecord, Depends(require_admin)]
) -> list[AdminDeviceResponse]:
    return [_admin_device_response(device) for device in request.app.state.auth_store.list_devices()]


@router.post(
    "/api/admin/devices/{device_id}/pairing-code",
    response_model=PairingCodeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_pairing_code(
    device_id: str,
    request: Request,
    current_user: Annotated[UserRecord, Depends(require_admin)],
) -> PairingCodeResponse:
    if request.app.state.auth_store.get_device(device_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DEVICE_NOT_FOUND_DETAIL)
    try:
        code = request.app.state.auth_store.create_pairing_code(device_id, current_user.id)
    except (PairingError, ValueError):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Device is unavailable for pairing") from None
    return PairingCodeResponse(device_id=device_id, code=code)


@router.delete("/api/admin/devices/{device_id}/owner", status_code=status.HTTP_204_NO_CONTENT)
def unbind_device(
    device_id: str,
    request: Request,
    _: Annotated[UserRecord, Depends(require_admin)],
) -> Response:
    if request.app.state.auth_store.unassign_device(device_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, DEVICE_NOT_FOUND_DETAIL)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _device_response(device: DeviceRecord) -> DeviceResponse:
    return DeviceResponse(device_id=device.device_id, last_seen_at=device.last_seen_at)


def _admin_device_response(device: DeviceRecord) -> AdminDeviceResponse:
    return AdminDeviceResponse(
        device_id=device.device_id,
        last_seen_at=device.last_seen_at,
        owner_user_id=device.owner_user_id,
    )
