import threading

import pytest
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from mydevagent.llm import FakeLLM
from mydevagent.orchestrator import Orchestrator
from mydevagent.tui.app import COMMANDS, TuiApp
from mydevagent.tui.apply import apply_answer
from mydevagent.tui.completion import DevCompleter
from mydevagent.tui.render import TurnRenderer, split_complete
from mydevagent.tui.session import Session, list_sessions


@pytest.fixture(autouse=True)
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("MYDEVAGENT_STATE_DIR", str(tmp_path / "state"))


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "calc.py").write_text("def add(a, b): return a + b\n")
    return root


def record_console():
    return Console(record=True, width=100, force_terminal=False, color_system=None)


def completions(completer, text):
    return [c.text for c in completer.get_completions(Document(text), None)]


def test_completer(registry, project):
    comp = DevCompleter(COMMANDS, dict(registry.by_alias), project)
    assert "/help" in completions(comp, "/he")
    assert completions(comp, "ciao /he") == []  # i comandi solo a inizio riga
    assert "@security" in completions(comp, "controlla @se")
    assert "@src/calc.py" in completions(comp, "migliora @sr")


def test_split_complete_respects_code_fences():
    done, tail = split_complete("intro\n\n```python\nx = 1\n\ny = 2\n")
    assert done == "intro\n\n" and tail.startswith("```python")
    done, tail = split_complete("a\n\nb\n\nc")
    assert done == "a\n\nb\n\n" and tail == "c"


def test_renderer_prints_agent_blocks():
    console = record_console()
    r = TurnRenderer(console, {"architect": "Architetto", "backend": "Backend"})
    r.on_event({"type": "route", "mode": "balanced", "agents": ["architect", "backend", "formatter"]})
    r.on_event({"type": "agent_end", "agent": "architect", "name": "Architetto", "ms": 1200,
                "prompt_tokens": 500, "completion_tokens": 300})
    r.on_event({"type": "tool_call", "agent": "backend", "tool": "web_search", "args": {"query": "fastapi"}})
    r.on_event({"type": "tool_result", "agent": "backend", "tool": "web_search", "ok": True, "preview": "[1] FastAPI"})
    r.on_chunk("**Summary**: ok.\n\n```python\nprint(1)\n```")
    r.on_event({"type": "done", "summary": "balanced · 2 agenti"})
    r.finish()
    out = console.export_text()
    assert "⏺ Team balanced · 2 agenti" in out and "Architetto → Backend" in out
    assert "⏺ Architetto" in out and "⎿  1.2s · 800 tok" in out
    assert "Web(fastapi)" in out and "print(1)" in out
    assert r.answer.startswith("**Summary**")


def test_apply_writes_only_after_confirmation(registry, project):
    console = record_console()
    answer = ("```python file=src/calc.py\ndef add(a: int, b: int) -> int:\n    return a + b\n```\n"
              "```python file=src/new.py\nX = 1\n```\n"
              "```python file=../escape.py\nboom\n```")
    answers = iter(["3", "1"])
    written = apply_answer(answer, registry, project, console, lambda q: next(answers))
    assert written == ["src/new.py"]
    assert (project / "src" / "calc.py").read_text() == "def add(a, b): return a + b\n"  # rifiutato
    assert not (project.parent / "escape.py").exists()
    out = console.export_text()
    assert "Update(src/calc.py)" in out and "+def add(a: int, b: int) -> int:" in out and "Bloccato ../escape.py" in out


def test_apply_all(registry, project):
    answer = "```python file=a.py\nA = 1\n```\n```python file=b.py\nB = 2\n```"
    asked = []
    written = apply_answer(answer, registry, project, record_console(), lambda q: asked.append(q) or "2")
    assert written == ["a.py", "b.py"] and len(asked) == 1


def test_cancel_stops_team_before_next_agent(settings):
    cancel = threading.Event()
    llm = FakeLLM()
    events = []

    def on_event(e):
        events.append(e)
        if e["type"] == "agent_end" and e["agent"] == "architect":
            cancel.set()

    out = "".join(Orchestrator(settings, llm=llm).run(
        "Crea un endpoint FastAPI con tabella users su Postgres", on_event=on_event, cancel=cancel))
    assert out == ""
    assert [c["role"] for c in llm.calls] == ["Architect"]
    assert events[-1]["type"] == "cancelled"


def test_cancel_stops_streaming(settings):
    cancel = threading.Event()
    chunks = []
    for chunk in Orchestrator(settings, llm=FakeLLM()).run("/fast somma in python", cancel=cancel):
        chunks.append(chunk)
        cancel.set()
    assert len(chunks) == 1


def test_sessions_roundtrip(project):
    s = Session(cwd=str(project))
    s.add_turn("ciao", "risposta")
    loaded = list_sessions(str(project))
    assert loaded[0].id == s.id and loaded[0].title == "ciao"
    assert "## MyDevAgent" in s.to_markdown()


def test_full_session_scripted(settings, project):
    console = record_console()
    orch = Orchestrator(settings, llm=FakeLLM())
    with create_pipe_input() as pipe:
        app = TuiApp(orch, console=console, prompt_input=pipe, prompt_output=DummyOutput(),
                     ask=lambda q: "1", root=project, background=False)
        pipe.send_text("/help\r")
        pipe.send_text("/balanced migliora @src/calc.py\r")
        pipe.send_text("/apply\r")
        pipe.send_text("!echo hello-shell\r")
        pipe.send_text("/cost\r")
        pipe.send_text("/deep\r")
        pipe.send_text("/export\r")
        pipe.send_text("/exit\r")
        app.loop()
    out = console.export_text()
    assert "Benvenuto in MyDevAgent" in out and "/apply" in out
    assert "allegato src/calc.py" in out and "⏺ Team balanced" in out
    assert (project / "app" / "main.py").is_file()  # scritto da /apply
    assert "hello-shell" in out and "$ echo hello-shell" in app.pending_context
    assert app.mode == "deep" and app.stats["turns"] == 1
    assert list(project.glob("mydevagent-*.md"))
    user_msgs = [m["content"] for m in app.session.history if m["role"] == "user"]
    assert user_msgs == ["/balanced migliora @src/calc.py"]
