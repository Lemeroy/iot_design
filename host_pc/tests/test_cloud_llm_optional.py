import importlib
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "cloud" / "backend"


def test_advisor_falls_back_when_openai_sdk_is_unavailable(monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    monkeypatch.setitem(sys.modules, "openai", None)
    sys.modules.pop("app.llm_advice", None)

    module = importlib.import_module("app.llm_advice")
    advisor = module.DoubaoAdvisor(api_key="")

    assert advisor.available is False
    assert advisor._client is None


def test_advisor_retries_after_transient_failure_without_exposing_provider_error(monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    module = importlib.import_module("app.llm_advice")
    schemas = importlib.import_module("app.schemas")

    class FailingCompletions:
        @staticmethod
        def create(**kwargs):
            raise RuntimeError("sensitive provider 401 request id")

    class FailingClient:
        class Chat:
            completions = FailingCompletions()

        chat = Chat()

    advisor = module.DoubaoAdvisor(api_key="")
    advisor.available = True
    advisor._client = FailingClient()
    text, _ = advisor.generate(
        schemas.Scores(face=72, speech=68, tongue=80, eye=85, csi=76, final=73),
        "warning",
        schemas.Profile(age=68, gender="other", conditions=["hypertension"]),
        [],
    )

    assert advisor.available is True
    assert "sensitive provider" not in text
    assert "request id" not in text


def test_advisor_requires_endpoint_id_when_api_key_is_present(monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    monkeypatch.delenv("VOLC_ARK_MODEL", raising=False)
    module = importlib.import_module("app.llm_advice")

    advisor = module.DoubaoAdvisor(api_key="configured-key", model="")

    assert advisor.model == ""
    assert advisor.available is False


def test_advisor_limits_chinese_advice_by_utf8_bytes(monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    module = importlib.import_module("app.llm_advice")
    schemas = importlib.import_module("app.schemas")

    long_chinese_text = "\u5065" * 240

    class LongCompletions:
        @staticmethod
        def create(**kwargs):
            message = SimpleNamespace(content=long_chinese_text)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    class LongAdviceClient:
        chat = SimpleNamespace(completions=LongCompletions())

    advisor = module.DoubaoAdvisor(api_key="")
    advisor.available = True
    advisor._client = LongAdviceClient()
    text, _ = advisor.generate(
        schemas.Scores(face=82, speech=78, tongue=85, eye=88, csi=80, final=82),
        "normal",
        schemas.Profile(age=68, gender="other", conditions=["hypertension"]),
        [],
    )

    assert len(text.encode("utf-8")) <= 384
    assert text.endswith("...")
    assert text.encode("utf-8").decode("utf-8") == text


def test_system_prompt_forbids_inventing_unlisted_medication(monkeypatch):
    monkeypatch.syspath_prepend(str(BACKEND))
    module = importlib.import_module("app.llm_advice")

    assert "meds 为空" in module.SYSTEM_PROMPT
    assert "不得推断用户未提供的用药" in module.SYSTEM_PROMPT
