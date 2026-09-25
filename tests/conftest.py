import pytest

from mydevagent.config import load_settings
from mydevagent.llm import FakeLLM
from mydevagent.orchestrator import Orchestrator
from mydevagent.registry import load_registry


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MYDEVAGENT_OFFLINE", "1")
    monkeypatch.delenv("MYDEVAGENT_API_KEY", raising=False)


@pytest.fixture
def settings(tmp_path):
    return load_settings(overrides={
        "tools": {
            "sandbox": {"backend": "local", "allow_unsafe_local": True, "timeout_s": 10},
            "filesystem": {"root": str(tmp_path)},
        }
    })


@pytest.fixture
def registry(settings):
    return load_registry(settings)


@pytest.fixture
def fake_llm():
    return FakeLLM()


@pytest.fixture
def orchestrator(settings, fake_llm):
    return Orchestrator(settings, llm=fake_llm)
