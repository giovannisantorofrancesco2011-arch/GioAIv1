import re
from dataclasses import dataclass, field

import pytest

from mydevagent.agent import AgentLoop, AgentTools, CheckpointStore, PermissionPolicy
from mydevagent.agent.context import RepoMap, append_memory, project_context, python_symbols, read_memory
from mydevagent.agent.permissions import is_dangerous
from mydevagent.agent.protocol import parse_text_calls
from mydevagent.agent.runner import AgentRunner
from mydevagent.agent.tools import apply_edit, detect_test_command
from mydevagent.llm import Completion, FakeLLM
from mydevagent.orchestrator import Orchestrator


@dataclass
class ScriptedLLM(FakeLLM):
    """Passi dell'agente da una lista; le chiamate del team (architect, gate) come FakeLLM."""

    steps: list[str] = field(default_factory=list)

    def complete(self, messages, *, tier="main", max_tokens=1024, temperature=0.2, tools=None):
        system = messages[0]["content"]
        if "(agent mode)" in system:
            self.calls.append({"role": "agent", "messages": [dict(m) for m in messages]})
            text = self.steps.pop(0) if self.steps else "Fatto."
            return Completion(text=text, prompt_tokens=10, completion_tokens=5)
        return super().complete(messages, tier=tier, max_tokens=max_tokens, temperature=temperature)


def T(name, **args):
    import json
    return f'<tool name="{name}">{json.dumps(args)}</tool>'


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    (root / "test_calc.py").write_text("from src.calc import add\n\ndef test_add():\n    assert add(2, 3) == 5\n")
    (root / "pyproject.toml").write_text("[project]\nname='demo'\n")
    (root / ".env").write_text("SECRET=1\n")
    return root


def make_tools(root, mode="auto", approver=None, events=None):
    return AgentTools(root, PermissionPolicy(mode=mode, root=root), CheckpointStore(root), approver=approver,
                      emit=(events.append if events is not None else None))


# ------------------------------------------------------------------ protocollo
def test_parse_text_calls_tolerant():
    text = 'Leggo il file.\n<tool name="read_file">{"path": "a.py",}</tool>\n<tool name="bash">{"command": "ls"'
    visible, calls = parse_text_calls(text)
    assert visible == "Leggo il file."
    assert [(c.name, c.args) for c in calls] == [("read_file", {"path": "a.py"}), ("bash", {"command": "ls"})] \
        or calls[1].error  # blocco non chiuso: letto o errore chiaro
    _, bad = parse_text_calls('<tool name="edit_file">{not json}</tool>')
    assert bad[0].error and "valid JSON" in bad[0].error
    _, multiline = parse_text_calls('<tool name="write_file">{"path": "a.py", "content": "x = 1\ny = 2"}</tool>')
    assert multiline[0].args["content"] == "x = 1\ny = 2"


# ------------------------------------------------------------------------ edit
def test_apply_edit_exact_ambiguous_and_whitespace():
    text = "def f():\n    return 1\n\ndef g():\n    return 1\n"
    assert apply_edit(text, "return 1", "return 2")[1].startswith("old_string matches 2")
    new, err = apply_edit(text, "def g():\n    return 1", "def g():\n    return 2")
    assert err is None and new.endswith("return 2\n")
    new, err = apply_edit(text, "def f():   \n    return 1  ", "def f():\n    return 3")
    assert err is None and "return 3" in new
    new, err = apply_edit("class A:\n    def m(self):\n        pass\n", "def m(self):\n    pass",
                          "def m(self):\n    return 42")
    assert err is None and "        return 42" in new
    _, err = apply_edit(text, "def h():", "x")
    assert "not found" in err and "Similar lines" in err


def test_tools_edit_write_and_checkpoint(project):
    events = []
    tools = make_tools(project, events=events)
    assert "    1→def add(a, b):" in tools.execute("read_file", {"path": "src/calc.py"})
    out = tools.execute("edit_file", {"path": "src/calc.py", "old_string": "def add(a, b):",
                                      "new_string": "def add(a: int, b: int) -> int:"})
    assert out.startswith("updated src/calc.py")
    tools.execute("write_file", {"path": "src/new.py", "content": "X = 1\n"})
    assert (project / "src" / "new.py").read_text() == "X = 1\n"
    assert any(e["type"] == "diff" and e["path"] == "src/calc.py" and e["added"] == 1 for e in events)
    store = tools.checkpoints
    cp, restored = store.undo()
    assert sorted(restored) == ["src/calc.py", "src/new.py"]
    assert (project / "src" / "calc.py").read_text().startswith("def add(a, b):")
    assert not (project / "src" / "new.py").exists()


def test_tools_refuse_secrets_and_escape(project):
    tools = make_tools(project)
    assert tools.execute("read_file", {"path": ".env"}).startswith("ERROR")
    assert tools.execute("write_file", {"path": "../evil.py", "content": "x"}).startswith("ERROR")
    assert tools.execute("nope", {}).startswith("ERROR: unknown tool")


# ------------------------------------------------------------------- permessi
def test_permission_modes(project):
    asked = []

    def approver(req):
        asked.append(req)
        return ("no", "usa un altro nome")

    tools = make_tools(project, mode="ask", approver=approver)
    out = tools.execute("write_file", {"path": "a.py", "content": "x"})
    assert out.startswith("DENIED") and "usa un altro nome" in out and asked[0].diff.startswith("---")
    assert tools.execute("bash", {"command": "ls"}).startswith("exit code 0")  # sola lettura: consentito
    plan = make_tools(project, mode="plan")
    assert plan.execute("write_file", {"path": "a.py", "content": "x"}).startswith("DENIED: plan mode")
    assert "edit_file" not in [s["name"] for s in plan.specs()]
    auto = make_tools(project, mode="auto")  # comandi pericolosi: sempre conferma
    assert auto.execute("bash", {"command": "rm -rf src"}).startswith("DENIED")
    assert (project / "src").exists()
    assert is_dangerous("git push --force origin main") and not is_dangerous("pytest -q")


def test_always_rule_is_persisted(project):
    tools = make_tools(project, mode="ask", approver=lambda req: ("always", ""))
    tools.execute("bash", {"command": "python -c 'print(1)'"})
    policy = PermissionPolicy(mode="ask", root=project)
    assert policy.decide("bash", {"command": "python -V"}).action == "allow"


def test_detect_tests_and_run(project):
    assert detect_test_command(project) == "python -m pytest -q"
    assert detect_test_command(project, "## Comandi\n- test: `make check`") == "make check"


# ------------------------------------------------------------------ contesto
def test_repo_map_and_memory(project):
    (project / "web").mkdir()
    (project / "web" / "api.ts").write_text("export async function getUser(id: string) {\n}\nexport class Api {}\n")
    repo_map = RepoMap(project).build("user api")
    assert "web/api.ts" in repo_map and "getUser(id: string)" in repo_map and "def add(a, b)" in repo_map
    assert repo_map.index("web/api.ts") < repo_map.index("src/calc.py")  # rilevanza per la richiesta
    append_memory(project, "usa sempre type hints")
    assert "usa sempre type hints" in read_memory(project)
    assert "# Project memory" in project_context(project)
    assert python_symbols("class A:\n    def m(self, x): pass\n") == ["class A", "  def m(self, x)"]


# ---------------------------------------------------------------------- loop
def test_agent_loop_edits_and_tests(project):
    llm = ScriptedLLM(steps=[
        "Guardo il codice.\n" + T("read_file", path="src/calc.py"),
        T("edit_file", path="src/calc.py", old_string="def add(a, b):", new_string="def add(a: int, b: int) -> int:")
        + T("run_tests"),
        "Ho aggiunto i type hint a `add`; test passati.",
    ])
    events = []
    tools = make_tools(project, events=events)
    result = AgentLoop(llm, tools, system="# Role: test", emit=events.append).run("aggiungi type hints")
    assert result.stopped == "done" and result.steps == 3 and result.tool_calls == 3
    assert "type hint" in result.text and result.changed == ["src/calc.py"]
    assert tools.last_test and tools.last_test[1] is True
    assert '<result name="read_file">' in llm.calls[1]["messages"][-1]["content"]


def test_agent_loop_stops_repeated_calls_and_max_steps(project):
    llm = ScriptedLLM(steps=[T("grep", pattern="zzz")] * 10)
    result = AgentLoop(llm, make_tools(project), system="# Role: t", max_steps=4).run("cerca")
    assert result.stopped == "max_steps"
    assert any("repeated the same tool call" in str(m["content"]) for c in llm.calls for m in c["messages"])


# -------------------------------------------------------------------- runner
def test_runner_balanced_reviews_real_diff_and_fixes(project, settings):
    llm = ScriptedLLM(
        steps=[T("write_file", path="src/util.py", content="def double(x):\n    return x * 2\n"),
               "Creato util.py",
               T("edit_file", path="src/util.py", old_string="def double(x):", new_string="def double(x: int) -> int:"),
               "Corretto con type hints"],
        gate_verdicts=["REVISE", "APPROVE"])
    orch = Orchestrator(settings, llm=llm)
    runner = AgentRunner(orch, project, PermissionPolicy(mode="auto", root=project))
    events = []
    out = "".join(runner.run("Crea un endpoint FastAPI con tabella users su Postgres", on_event=events.append))
    reviewer_input = [c for c in llm.calls if c.get("role", "").startswith("Code Reviewer")][0]["messages"][1]["content"]
    assert "+def double(x):" in reviewer_input  # il reviewer vede il diff reale
    assert (project / "src" / "util.py").read_text().startswith("def double(x: int) -> int:")
    assert "Corretto con type hints" in out and "✅ Review: approvata" in out
    assert "📝 File modificati: src/util.py" in out
    assert any(e["type"] == "info" and e["text"].startswith("revisione 1") for e in events)
    assert llm.calls[0]["role"].startswith("Architect")


def test_runner_fast_mode_single_agent(project, settings):
    llm = ScriptedLLM(steps=["La funzione add somma due numeri."])
    runner = AgentRunner(Orchestrator(settings, llm=llm), project, PermissionPolicy(mode="ask", root=project))
    out = "".join(runner.run("cosa fa add in python?"))
    assert out.startswith("La funzione add") and [c["role"] for c in llm.calls] == ["agent"]
    system = llm.calls[0]["messages"][0]["content"]
    assert "# Repository map" in system and "src/calc.py" in system


def test_runner_cancel(project, settings):
    import threading
    cancel = threading.Event()
    cancel.set()
    llm = ScriptedLLM(steps=["x"])
    events = []
    out = "".join(AgentRunner(Orchestrator(settings, llm=llm), project, PermissionPolicy(root=project)).run(
        "ciao", on_event=events.append, cancel=cancel))
    assert out == "" and events[-1]["type"] == "cancelled"
    assert re.search("cancelled", str(events))


def test_agent_nudges_when_model_pastes_code(project):
    llm = ScriptedLLM(steps=[
        "Ecco il codice:\n```python\ndef sub(a, b):\n    return a - b\n```",
        T("edit_file", path="src/calc.py", old_string="def add(a, b):\n    return a + b",
          new_string="def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b"),
        "Aggiunta sub in src/calc.py.",
    ])
    result = AgentLoop(llm, make_tools(project), system="# Role: t").run("aggiungi sub")
    assert result.text == "Aggiunta sub in src/calc.py." and result.changed == ["src/calc.py"]
    assert "def sub" in (project / "src" / "calc.py").read_text()


# ------------------------------------------------------------------ ultra-deep
@dataclass
class UltraLLM(ScriptedLLM):
    integrator: list[str] = field(default_factory=list)

    def _answer(self, role, messages):
        if role.startswith("Chief Integrator"):
            return self.integrator.pop(0) if self.integrator else "DECISION: SHIP\n- [MINOR] x: y\nDropped: none"
        if role.startswith("Devil"):
            return "**Verdict**: ADJUST — add input validation"
        return super()._answer(role, messages)


def test_ultra_deep_agent_mode_runs_all_35_agents(project, settings):
    llm = UltraLLM(
        steps=[T("write_file", path="src/util.py", content="def double(x):\n    return x * 2\n"), "Creato util.py",
               T("edit_file", path="src/util.py", old_string="def double(x):", new_string="def double(x: int) -> int:"),
               "Corretto", "Docs ok"],
        integrator=["DECISION: FIX\n- [MAJOR] src/util.py: add type hints (from: reviewer)\nDropped: none",
                    "DECISION: SHIP\n- [MINOR] naming\nDropped: none"])
    orch = Orchestrator(settings, llm=llm)
    events = []
    out = "".join(AgentRunner(orch, project, PermissionPolicy(mode="auto", root=project)).run(
        "/ultra-deep crea una funzione double", on_event=events.append))
    roles = {c["role"] for c in llm.calls}
    for role in ("Requirements Analyst", "Architect", "Devil's Advocate", "Test Strategist", "Chief Integrator",
                 "Web Fact-checker", "Dependencies & Supply-chain agent", "Threat Modeling & Privacy reviewer",
                 "Release & Versioning agent", "Documentation", "Output Formatter & Final Delivery",
                 "Mobile Engineer", "Security reviewer"):
        assert any(r.startswith(role) for r in roles), role
    done = [e for e in events if e["type"] == "done"][-1]["summary"]
    assert done.startswith("ultra-deep · 35 agenti")
    assert (project / "src" / "util.py").read_text().startswith("def double(x: int) -> int:")
    assert any(e["type"] == "info" and e["text"].startswith("correzioni, giro 1") for e in events)
    assert any(e["type"] == "agent_skip" and e["agent"] == "research" for e in events)  # offline nei test
    assert "📝 File modificati: src/util.py" in out
    lens = [c for c in llm.calls if c["role"].startswith("Mobile Engineer")][0]
    assert "Quick lens review" in lens["messages"][1]["content"]


def test_ultra_deep_chat_mode(settings):
    llm = UltraLLM()
    orch = Orchestrator(settings, llm=llm)
    out = orch.ask("/ultra-deep crea un endpoint FastAPI")
    assert orch.last_run.route.mode == "ultra-deep"
    assert "def add" in out and "Sandbox" in out
    assert len({c["role"] for c in llm.calls}) >= 30


def test_router_ultra(settings, registry):
    from mydevagent.router import Router

    router = Router(settings, registry)
    r = router.route("/ultra-deep app mobile con react native e flutter")
    assert r.mode == "ultra-deep" and "mobile" in r.ultra_relevant
    assert router.route("crea una app mobile con react native").mode != "ultra-deep"  # mai automatica
    assert "mobile" not in router.route("app react native semplice").scores  # estesi fuori dalle modalità normali
    assert router.route("sistema enterprise production-ready con audit completo").suggest_ultra
