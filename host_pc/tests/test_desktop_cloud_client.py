from __future__ import annotations

import httpx
import pytest


def _transport(handler):
    return httpx.MockTransport(handler)


def test_cloud_client_login_connect_and_fetch_preserves_missing_scores():
    from stroke_host.demo.cloud_client import CloudClient

    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/demo/api/login":
            return httpx.Response(
                200,
                json={"authenticated": True, "device_id": None},
                headers={"set-cookie": "sg_demo_session=token; Path=/; HttpOnly"},
            )
        if request.url.path == "/demo/api/connect":
            assert request.read() == b'{"device_id":"sg-0001"}'
            return httpx.Response(200, json={"authenticated": True, "device_id": "sg-0001"})
        if request.url.path == "/demo/api/device":
            return httpx.Response(
                200,
                json={
                    "device_id": "sg-0001",
                    "online": True,
                    "received_at": 1_789_000_000.5,
                    "scores": {
                        "face": None,
                        "speech": None,
                        "tongue": None,
                        "eye": None,
                        "csi": 36,
                        "final": 0,
                    },
                    "level": "insufficient",
                    "reasons": ["insufficient_modalities"],
                    "veto_by": [],
                    "advice": {
                        "advice_text": "请保持观察，如突发症状立即拨打120。",
                        "source": "doubao-lite",
                        "ts": 1_789_000_001,
                    },
                },
            )
        raise AssertionError(request.url.path)

    client = CloudClient("http://demo.test", transport=_transport(handler))
    client.login("demo", "secret")
    client.connect("sg-0001")
    snapshot = client.fetch_device()

    assert requests == [
        ("POST", "/demo/api/login"),
        ("POST", "/demo/api/connect"),
        ("GET", "/demo/api/device"),
    ]
    assert snapshot.device_id == "sg-0001"
    assert snapshot.online is True
    assert snapshot.scores.face is None
    assert snapshot.scores.speech is None
    assert snapshot.scores.tongue is None
    assert snapshot.scores.eye is None
    assert snapshot.scores.csi == 36
    assert snapshot.scores.final == 0
    assert snapshot.level == "insufficient"
    assert snapshot.advice is not None
    assert snapshot.advice.source == "doubao-lite"


@pytest.mark.parametrize("operation", ["login", "connect", "fetch_device"])
def test_cloud_client_maps_unauthorized_to_authentication_required(operation):
    from stroke_host.demo.cloud_client import AuthenticationRequired, CloudClient

    client = CloudClient(
        "http://demo.test",
        transport=_transport(lambda request: httpx.Response(401, json={"detail": "no"})),
    )

    with pytest.raises(AuthenticationRequired):
        if operation == "login":
            client.login("demo", "wrong")
        elif operation == "connect":
            client.connect("sg-0001")
        else:
            client.fetch_device()


@pytest.mark.parametrize("status_code", [404, 409])
def test_cloud_client_maps_connect_not_found_or_offline_to_device_offline(status_code):
    from stroke_host.demo.cloud_client import CloudClient, DeviceOffline

    client = CloudClient(
        "http://demo.test",
        transport=_transport(lambda request: httpx.Response(status_code, json={"detail": "offline"})),
    )

    with pytest.raises(DeviceOffline):
        client.connect("sg-0001")


def test_cloud_client_returns_explicit_offline_snapshot_without_scores():
    from stroke_host.demo.cloud_client import CloudClient

    client = CloudClient(
        "http://demo.test",
        transport=_transport(
            lambda request: httpx.Response(
                200,
                json={
                    "device_id": "sg-0001",
                    "online": False,
                    "received_at": 1_789_000_000.5,
                    "scores": None,
                    "level": None,
                    "reasons": [],
                    "veto_by": [],
                    "advice": None,
                },
            )
        ),
    )

    snapshot = client.fetch_device()

    assert snapshot.online is False
    assert snapshot.scores is None
    assert snapshot.level is None


def test_cloud_client_maps_transport_failure_to_cloud_unavailable():
    from stroke_host.demo.cloud_client import CloudClient, CloudUnavailable

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)

    client = CloudClient("http://demo.test", transport=_transport(handler))

    with pytest.raises(CloudUnavailable):
        client.fetch_device()


def test_cloud_client_logout_closes_remote_session():
    from stroke_host.demo.cloud_client import CloudClient

    called = []

    def handler(request: httpx.Request) -> httpx.Response:
        called.append((request.method, request.url.path))
        return httpx.Response(200, json={"authenticated": False, "device_id": None})

    client = CloudClient("http://demo.test", transport=_transport(handler))
    client.logout()

    assert called == [("POST", "/demo/api/logout")]
