"""TTS 封装测试 (不真的出声, 打桩 pyttsx3)."""
import sys
import time
import types

import pytest


def _make_stub_pyttsx3():
    """插入一个假 pyttsx3, 记录 say/runAndWait 调用."""
    mod = types.ModuleType("pyttsx3")
    log = []

    class FakeEngine:
        def __init__(self):
            self.props = {}
        def init(self):
            return self
        def setProperty(self, k, v):
            self.props[k] = v
        def getProperty(self, k):
            if k == "voices":
                v = types.SimpleNamespace(name="Test", id="test-voice")
                return [v]
            return self.props.get(k)
        def say(self, text):
            log.append(("say", text))
        def runAndWait(self):
            log.append(("wait",))
        def stop(self):
            log.append(("stop",))

    fe = FakeEngine()
    mod.init = lambda: fe
    mod._log = log
    mod._engine = fe
    return mod


@pytest.fixture
def fake_pyttsx3(monkeypatch):
    mod = _make_stub_pyttsx3()
    monkeypatch.setitem(sys.modules, "pyttsx3", mod)
    return mod


def test_tts_disabled_when_pyttsx3_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "pyttsx3", None)  # ImportError shim
    from stroke_host.ui.tts import TtsWorker
    # 强制走 ImportError 分支: 直接删掉 pyttsx3 项
    monkeypatch.delitem(sys.modules, "pyttsx3", raising=False)
    # 阻止真正安装的 pyttsx3 被 import 到 (机器可能装了真的)
    import builtins
    real_import = builtins.__import__
    def _boom(name, *a, **kw):
        if name == "pyttsx3":
            raise ImportError("stub")
        return real_import(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", _boom)

    t = TtsWorker()
    t.open()
    assert not t.available
    t.speak("hello")  # no-op
    t.close()


def test_tts_speak_and_cooldown(fake_pyttsx3):
    from stroke_host.ui.tts import TtsWorker

    t = TtsWorker()
    t.open()
    assert t.available
    try:
        t.speak("危险,请立即就医")
        t.speak("危险,请立即就医")  # 冷却期内应被丢弃
        # 给后台线程时间
        deadline = time.time() + 2.0
        while len(fake_pyttsx3._log) < 2 and time.time() < deadline:
            time.sleep(0.05)
        says = [x for x in fake_pyttsx3._log if x[0] == "say"]
        assert len(says) == 1  # 只播一次
    finally:
        t.close()


def test_tts_force_bypasses_cooldown(fake_pyttsx3):
    from stroke_host.ui.tts import TtsWorker

    t = TtsWorker()
    t.open()
    try:
        t.speak("请微笑", force=True)
        t.speak("请微笑", force=True)
        deadline = time.time() + 2.0
        while len([x for x in fake_pyttsx3._log if x[0] == "say"]) < 2 \
                and time.time() < deadline:
            time.sleep(0.05)
        says = [x for x in fake_pyttsx3._log if x[0] == "say"]
        assert len(says) == 2
    finally:
        t.close()


def test_tts_close_idempotent(fake_pyttsx3):
    from stroke_host.ui.tts import TtsWorker

    t = TtsWorker()
    t.open()
    t.close()
    t.close()  # 不应抛
