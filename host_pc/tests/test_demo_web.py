from __future__ import annotations

import os
import re
import sys
import time
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "cloud" / "backend" / "app"
STATIC = BACKEND / "static" / "demo"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_demo_web_assets_define_the_read_only_monitor_contract():
    main = _read(BACKEND / "main.py")
    page = _read(STATIC / "index.html")
    css = _read(STATIC / "app.css")
    script = _read(STATIC / "app.js")
    bundled = "\n".join((main, page, css, script))

    assert "StaticFiles" in main
    assert 'mount("/demo"' in main
    assert 'href="/demo/app.css"' in page
    assert 'src="/demo/app.js"' in page
    assert "setInterval(pollDevice, 5000)" in script
    assert "setTimeout(pollDevice, 5000)" not in script
    assert "未接入" in bundled
    assert "立即拨打 120" in bundled
    assert "80" not in script
    assert "login" in script
    assert "connect" in script
    assert "disconnect" in script
    assert "logout" in script
    assert "/demo/api/device" in script
    assert "reasons" in script
    assert "veto_by" in script
    assert "advice" in script
    assert "aria-live" in page
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert "[hidden] { display: none !important; }" in css
    assert ".desk { width: 100%; max-width: 1180px;" in css
    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert ".score-tile:nth-child(3n)" in css
    assert ".topbar > *, .monitor-head > *, .state-strip > *, .monitor-actions { min-width: 0; }" in css

    for source in (page, css, script):
        assert "http://" not in source
        assert "https://" not in source


def test_demo_web_supports_guided_screening_with_websocket_fallback():
    page = _read(STATIC / "index.html")
    script = _read(STATIC / "app.js")

    for token in (
        'id="screening-start"',
        'id="screening-cancel"',
        'id="screening-instruction"',
        'id="screening-progress"',
    ):
        assert token in page
    assert 'request("/demo/api/screening"' in script
    assert 'sendScreening("start")' in script
    assert 'sendScreening("cancel")' in script
    assert "new WebSocket" in script
    assert 'request("/demo/api/device")' in script
    assert "setInterval(pollDevice, 5000)" in script
    assert "screening_stage" in script
    assert "function scoreValue(value, online, stage)" in script
    assert '"待采集"' in script
    assert '"本轮未完成"' in script
    for prompt in ("请正视镜面", "请看向左侧", "请看向右侧", "请张口伸舌", "筛查完成"):
        assert prompt in script
    for forbidden in ("simulate", "mockScore", "Math.random"):
        assert forbidden not in script


def test_demo_web_waits_for_a_new_fusion_before_showing_advice():
    script = _read(STATIC / "app.js")

    assert '"等待形成新的融合评分"' in script
    assert 'fields.adviceSource.textContent = advice && advice.source ? advice.source : "--"' in script
    assert 'fields.adviceTime.textContent = advice ? formatTime(advice.ts) : "--"' in script


def test_demo_web_guides_preliminary_speech_after_camera_stages():
    script = _read(STATIC / "app.js")

    assert "初赛声学筛查" in script
    assert "请朗读：今天的天气很好" in script
    assert "function renderScreening(stage, online, speechScore)" in script
    assert "normalized === 6 && !Number.isFinite(speechScore)" in script
    assert "renderScreening(stage, online, scores.speech)" in script


def test_demo_web_wraps_the_long_connected_device_id_on_small_screens():
    css = _read(STATIC / "app.css")

    connected_device_rule = re.search(r"#connected-device\s*\{([^}]*)\}", css)

    assert connected_device_rule
    assert "overflow-wrap: anywhere;" in connected_device_rule.group(1)
    assert "min-width: 0;" in connected_device_rule.group(1)


def test_demo_web_keeps_routine_poll_success_out_of_live_announcements():
    page = _read(STATIC / "index.html")
    script = _read(STATIC / "app.js")

    assert 'id="status-message"' in page
    assert 'id="status-message" class="status-message" aria-live' not in page
    assert 'id="live-message"' in page
    assert 'id="live-message" class="visually-hidden" aria-live="polite"' in page
    assert "function announce(message)" in script

    poll_success = re.search(
        r"const data = await request\(\"/demo/api/device\"\);(?P<body>.*?)\n    \} catch",
        script,
        re.DOTALL,
    )

    assert poll_success
    assert "renderDevice(data);" in poll_success.group("body")
    assert 'setStatus("监测数据已更新");' in poll_success.group("body")
    assert "announce(" not in poll_success.group("body")
    assert "liveMessage" not in poll_success.group("body")


def test_demo_web_view_transitions_focus_the_new_view_through_show_view():
    script = _read(STATIC / "app.js")

    assert re.search(
        r"const focusTargets = \{\s*"
        r"login: \"#username\",\s*"
        r"connect: \"#device-id\",\s*"
        r"monitor: \"#refresh-button\",\s*\}",
        script,
        re.DOTALL,
    )
    show_view = re.search(r"function showView\(name\) \{(?P<body>.*?)\n  \}", script, re.DOTALL)
    assert show_view
    assert "element.hidden = viewName !== name" in show_view.group("body")
    assert "const focusSelector = focusTargets[name]" in show_view.group("body")
    assert "document.querySelector(focusSelector)" in show_view.group("body")
    assert "target.focus();" in show_view.group("body")
    assert 'document.querySelector("#device-id").focus();' not in script

    for transition in (
        'showView("login");',
        'showView("connect");',
        'showView("monitor");',
    ):
        assert script.count(transition) >= 1
    assert 'if (error.status === 401) { showView("login");' in script
    assert 'if (error.status === 409) { showView("connect");' in script


def test_demo_web_logout_only_leaves_monitor_after_a_successful_or_unauthorized_response():
    page = _read(STATIC / "index.html")
    script = _read(STATIC / "app.js")

    assert 'id="connect-logout-button"' in page
    assert page.count('data-logout') == 2
    assert 'id="connect-logout-button" type="button"' in page

    logout_handler = re.search(
        r"async function handleLogout\(\) \{(?P<body>.*?)\n  \}",
        script,
        re.DOTALL,
    )

    assert logout_handler
    body = logout_handler.group("body")
    assert "await request(\"/demo/api/logout\", { method: \"POST\" })" in body
    assert "finally" not in body
    transaction = re.search(
        r"try \{(?P<success>.*?)\}\s*catch \(error\) \{(?P<failure>.*)\}",
        body,
        re.DOTALL,
    )
    assert transaction
    success = transaction.group("success")
    failure = transaction.group("failure")

    assert 'showView("login");' in success
    assert 'report("已退出登录");' in success
    assert 'if (error.status === 401) { showView("login");' in failure
    assert 'report("会话已结束，请重新登录");' in failure
    assert 'report("退出失败，请重试");' in failure
    assert 'showView("login");' not in failure.replace(
        'if (error.status === 401) { showView("login");', ""
    )
    assert "clearInterval" not in body
    assert "document.cookie" not in body
    assert "error.message" not in failure
    assert 'document.querySelectorAll("[data-logout]")' in script
    assert 'button.addEventListener("click", handleLogout)' in script


def run_fixture_server() -> None:
    """Serve deterministic monitor data for local screenshot inspection."""
    import uvicorn

    from cloud.backend.app.demo_auth import DemoAuth
    from cloud.backend.app.demo_api import router as demo_api_router
    from cloud.backend.app.demo_web import DEMO_STATIC_DIRECTORY
    from cloud.backend.app.schemas import DownlinkPayload, Profile, Scores, UplinkPayload
    from fastapi import FastAPI
    from fastapi.staticfiles import StaticFiles

    os.environ["SG_DEMO_USER"] = "demo"
    os.environ["SG_DEMO_PASSWORD"] = "demo-pass"
    os.environ["SG_DEMO_SESSION_SECRET"] = "fixture-secret-for-local-visual-inspection-only"
    os.environ["SG_ALLOW_INSECURE_HTTP"] = "1"

    class FixtureBridge:
        def __init__(self) -> None:
            self.snapshot = {
                "received_at": time.time(),
                "uplink": UplinkPayload(
                    scores=Scores(face=None, speech=71, tongue=None, eye=62, csi=69, final=58),
                    level="danger",
                    reasons=["综合评分风险提示"],
                    veto_by=["speech"],
                    profile=Profile(age=68),
                    device_id="sg-demo-01",
                    ts=1720000000,
                ),
                "advice": DownlinkPayload(
                    level="danger",
                    advice_text="出现风险提示，请及时就医评估；如有突发症状立即拨打 120。",
                    source="fixture-advisor",
                    ts=1720000000,
                ),
            }

        def cache_snapshot(self, device_id: str):
            if device_id != "sg-demo-01":
                return None
            snapshot = dict(self.snapshot)
            snapshot["received_at"] = time.time()
            return snapshot

    fixture_main = types.ModuleType("cloud.backend.app.main")
    fixture_main._demo_auth = DemoAuth.from_env()
    fixture_main._bridge = FixtureBridge()
    sys.modules[fixture_main.__name__] = fixture_main
    import cloud.backend.app as app_package

    app_package.main = fixture_main
    app = FastAPI()
    app.include_router(demo_api_router)
    app.mount("/demo", StaticFiles(directory=DEMO_STATIC_DIRECTORY, html=True), name="demo")
    uvicorn.run(app, host="127.0.0.1", port=8013, log_level="warning")


if __name__ == "__main__":
    run_fixture_server()
