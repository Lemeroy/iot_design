import json
import logging
from io import BytesIO
from urllib.error import URLError

import pytest

from cloud.backend.app.alert_policy import AlertCoordinator
from cloud.backend.app.pushplus import PushPlusNotifier
from cloud.backend.app.schemas import UplinkPayload


def _uplink(level: str = "warning") -> UplinkPayload:
    return UplinkPayload(**{
        "schema_version": 1,
        "scores": {
            "face": 42, "speech": 55, "tongue": 68,
            "eye": 61, "csi": 73, "final": 54,
        },
        "level": level,
        "profile": {
            "age": 68,
            "gender": "other",
            "conditions": ["private-condition"],
            "meds": ["private-medication"],
            "stroke_history": False,
        },
        "reasons": ["face score low"],
        "veto_by": [],
        "device_id": "sg-0001",
        "ts": 1784250000,
        "seq": 9,
        "screening_stage": 6,
    })


class _Response:
    def __init__(self, payload: bytes):
        self._body = BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int = -1) -> bytes:
        return self._body.read(limit)


def test_alerts_are_inactive_until_screening_starts():
    alerts = AlertCoordinator()

    assert alerts.observe("sg-0001", "danger") is None
    assert alerts.observe("sg-0001", "warning") is None


def test_warning_requires_three_consecutive_results_and_dispatches_once():
    alerts = AlertCoordinator()
    alerts.start("sg-0001")

    assert alerts.observe("sg-0001", "warning") is None
    assert alerts.observe("sg-0001", "warning") is None
    assert alerts.observe("sg-0001", "warning") == "warning"
    assert alerts.observe("sg-0001", "warning") is None

    alerts.mark_dispatched("sg-0001", "warning")
    assert alerts.observe("sg-0001", "warning") is None


def test_normal_and_insufficient_interrupt_warning_confirmation():
    for interrupting_level in ("normal", "insufficient"):
        alerts = AlertCoordinator()
        alerts.start("sg-0001")
        assert alerts.observe("sg-0001", "warning") is None
        assert alerts.observe("sg-0001", "warning") is None
        assert alerts.observe("sg-0001", interrupting_level) is None
        assert alerts.observe("sg-0001", "warning") is None
        assert alerts.observe("sg-0001", "warning") is None
        assert alerts.observe("sg-0001", "warning") == "warning"


def test_danger_is_immediate_and_warning_to_danger_escalates_once():
    alerts = AlertCoordinator()
    alerts.start("sg-0001")

    for _ in range(3):
        warning = alerts.observe("sg-0001", "warning")
    assert warning == "warning"
    alerts.mark_dispatched("sg-0001", "warning")

    assert alerts.observe("sg-0001", "danger") == "danger"
    assert alerts.observe("sg-0001", "danger") is None
    alerts.mark_dispatched("sg-0001", "danger")
    assert alerts.observe("sg-0001", "danger") is None


def test_cancel_deactivates_and_new_screening_resets_limits():
    alerts = AlertCoordinator()
    alerts.start("sg-0001")
    assert alerts.observe("sg-0001", "danger") == "danger"
    alerts.mark_dispatched("sg-0001", "danger")
    alerts.cancel("sg-0001")

    assert alerts.observe("sg-0001", "danger") is None
    alerts.start("sg-0001")
    assert alerts.observe("sg-0001", "danger") == "danger"


def test_alert_state_is_isolated_per_device():
    alerts = AlertCoordinator()
    alerts.start("sg-0001")
    alerts.start("sg-0002")

    assert alerts.observe("sg-0001", "warning") is None
    assert alerts.observe("sg-0001", "warning") is None
    assert alerts.observe("sg-0002", "warning") is None
    assert alerts.observe("sg-0001", "warning") == "warning"
    assert alerts.observe("sg-0002", "warning") is None


def test_pushplus_self_request_contains_only_approved_numeric_content():
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        return _Response(b'{"code":200,"msg":"request accepted","data":"serial-1"}')

    notifier = PushPlusNotifier(
        enabled=True,
        token="secret-token",
        device_name="StrokeGuard Mirror 1",
        opener=opener,
    )

    assert notifier.send("sg-0001", _uplink(), "Seek medical help promptly.")
    request, timeout = requests[0]
    body = json.loads(request.data.decode("utf-8"))
    assert request.full_url == "https://www.pushplus.plus/send"
    assert timeout == 8
    assert set(body) == {"token", "title", "content", "template", "channel"}
    assert body["token"] == "secret-token"
    assert body["template"] == "markdown"
    assert body["channel"] == "wechat"
    for expected in (
        "sg-0001", "StrokeGuard Mirror 1", "F: 42", "S: 55", "T: 68",
        "E: 61", "CSI: 73", "Final: 54", "warning",
        "Seek medical help promptly.", "risk reminder", "not a diagnosis",
    ):
        assert expected in body["content"]
    for forbidden in (
        "private-condition", "private-medication", "profile", "mfcc",
        "landmarks", "eye trajectories", "raw audio", "raw video",
    ):
        assert forbidden not in body["content"].lower()


def test_disabled_pushplus_never_opens_network():
    calls = []
    notifier = PushPlusNotifier(
        enabled=False,
        token="secret-token",
        opener=lambda *args, **kwargs: calls.append((args, kwargs)),
    )

    assert not notifier.send("sg-0001", _uplink(), "advice")
    assert calls == []


@pytest.mark.parametrize(
    "response",
    [
        b"not-json",
        b'{"code":903,"msg":"invalid token"}',
        b'{"code":905,"msg":"real name required"}',
    ],
)
def test_pushplus_rejects_malformed_and_provider_error_responses(response):
    notifier = PushPlusNotifier(
        enabled=True,
        token="secret-token",
        opener=lambda request, timeout: _Response(response),
    )

    assert not notifier.send("sg-0001", _uplink(), "private advice body")


def test_pushplus_network_failure_logs_neither_token_nor_body(caplog):
    def fail(request, timeout):
        raise URLError("network down")

    notifier = PushPlusNotifier(enabled=True, token="secret-token", opener=fail)
    with caplog.at_level(logging.WARNING):
        assert not notifier.send("sg-0001", _uplink(), "private advice body")

    assert "secret-token" not in caplog.text
    assert "private advice body" not in caplog.text


def test_pushplus_code_900_disables_further_process_attempts():
    calls = []

    def limited(request, timeout):
        calls.append(request)
        return _Response(b'{"code":900,"msg":"request limit"}')

    notifier = PushPlusNotifier(enabled=True, token="secret-token", opener=limited)

    assert not notifier.send("sg-0001", _uplink(), "advice")
    assert not notifier.enabled
    assert not notifier.send("sg-0001", _uplink(), "advice")
    assert len(calls) == 1
