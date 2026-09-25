import importlib.util
import json
import shutil
import sys
from pathlib import Path

import httpx
import openai
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from mydevagent import health
from mydevagent.llm import FakeLLM
from mydevagent.orchestrator import Orchestrator
from mydevagent.tui.app import TuiApp

FINETUNE = Path(__file__).resolve().parents[1] / "finetune"
MYCODE = FINETUNE / "mycode"


def load(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


md_to_model = load(FINETUNE / "md_to_model.py")
check_data = load(MYCODE / "check_data.py")
crea_mycode = load(MYCODE / "crea_mycode.py")
SYSTEM = (MYCODE / "SYSTEM.txt").read_text(encoding="utf-8").strip()
AGENT = (MYCODE / "AGENT_SYSTEM.txt").read_text(encoding="utf-8").strip()


def test_pieces_cut_at_line_ends():
    text = "riga uno\nriga due\nriga tre\n"
    parts = md_to_model.pieces(text, 12)
    assert "".join(parts) == text and all(p.endswith("\n") for p in parts)
    assert md_to_model.pieces("x" * 25, 10) == ["x" * 10, "x" * 10, "x" * 5]


def test_parse_examples_tolerates_chatter():
    raw = 'Ecco: {"examples": [{"user": "come stai?", "assistant": "Bene, su cosa lavori?"}, {"user": "x"}]} fine'
    assert md_to_model.parse_examples(raw) == [{"user": "come stai?", "assistant": "Bene, su cosa lavori?"}]
    assert md_to_model.parse_examples("niente json") == []


class FakeTeacher:
    calls = 0

    def __init__(self, *args, **kwargs):
        pass

    def ask(self, system, user, *, json_mode=False, temperature=0.3):
        FakeTeacher.calls += 1
        if "take precise notes" in system:
            return "## Behavior\n- Lead with the answer."
        if json_mode:
            return json.dumps({"examples": [{"user": "Cos'è una lista?", "assistant": "Una sequenza ordinata."}]})
        return "# Who you are\nYou are MyCode.\n# How you talk\n- Lead with the answer."


def test_md_to_model_writes_manual_and_dataset_once(tmp_path, monkeypatch, capsys):
    out = tmp_path / "mycode"
    out.mkdir()
    shutil.copy(MYCODE / "SYSTEM.txt", out / "SYSTEM.txt")
    (out / "MANUALE.md").write_text("# Who you are\nold\n", encoding="utf-8")
    src = tmp_path / "regole.md"
    src.write_text("# Regole\nRispondi subito.\n", encoding="utf-8")
    monkeypatch.setattr(md_to_model, "Teacher", FakeTeacher)
    monkeypatch.setattr(sys, "argv", ["md_to_model.py", str(src), "--out", str(out)])

    md_to_model.main()
    data = out / "data" / "generated.jsonl"
    rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1 and check_data.check_row(rows[0], SYSTEM, AGENT) == ("chat", [])
    assert "You are MyCode" in (out / "MANUALE.md").read_text(encoding="utf-8")
    assert "old" in (out / "MANUALE.bak.md").read_text(encoding="utf-8")

    calls = FakeTeacher.calls
    md_to_model.main()  # stessi file: tutto dalla cache, niente doppioni
    assert FakeTeacher.calls == calls
    assert len(data.read_text(encoding="utf-8").splitlines()) == 1


def test_check_row_catches_broken_agent_examples():
    def row(*turns):
        return {"messages": [{"role": "system", "content": AGENT}]
                + [{"role": ("user", "assistant")[i % 2], "content": t} for i, t in enumerate(turns)], "source": "t"}

    good = row("leggi app.py", '<tool name="read_file">{"path": "app.py"}</tool>',
               '<result name="read_file">\napp.py (1 lines)\n    1→x = 1\n</result>', "Contiene `x = 1`.")
    assert check_data.check_row(good, SYSTEM, AGENT) == ("agent", [])
    unknown = row("fai", '<tool name="rm_all">{}</tool>', '<result name="rm_all">\nok\n</result>', "Fatto.")
    assert any("sconosciuto" in e for e in check_data.check_row(unknown, SYSTEM, AGENT)[1])
    mismatch = row("fai", '<tool name="grep">{"pattern": "x"}</tool>',
                   '<result name="bash">\nexit code 0\n</result>', "Fatto.")
    assert check_data.check_row(mismatch, SYSTEM, AGENT)[1]
    last_call = row("fai", '<tool name="grep">{"pattern": "x"}</tool>')
    assert any("finale" in e for e in check_data.check_row(last_call, SYSTEM, AGENT)[1])


def test_committed_dataset_is_valid():
    files = sorted((MYCODE / "data").glob("*.jsonl"))
    assert any(f.name == "train.jsonl" for f in files)
    seen, bad = set(), []
    for path in files:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            row = json.loads(line)
            first = row["messages"][1]["content"].strip().lower()
            errors = check_data.check_row(row, SYSTEM, AGENT)[1] + (["duplicata"] if first in seen else [])
            seen.add(first)
            if errors:
                bad.append(f"{path.name}:{n}: {errors}")
    assert not bad, bad[:5]


def test_modelfile_copies_base_template_and_stops(monkeypatch):
    answers = {"--template": "{{ .Prompt }}", "--parameters": 'stop                           "<|im_end|>"\n'
                                                               "temperature                    0.7\n"}
    monkeypatch.setattr(crea_mycode, "ollama", lambda *args: answers.get(args[-1]))
    text = crea_mycode.modelfile("./mycode.gguf", with_template=True)
    assert text.startswith("FROM ./mycode.gguf\n") and 'TEMPLATE """{{ .Prompt }}"""' in text
    assert 'PARAMETER stop "<|im_end|>"' in text and "PARAMETER num_ctx 16384" in text
    assert 'SYSTEM """You are MyCode' in text and "# How you talk" in text

    monkeypatch.setattr(crea_mycode, "ollama", lambda *args: None)
    text = crea_mycode.modelfile("./mycode.gguf", with_template=True)
    assert "<|im_start|>assistant" in text and 'PARAMETER stop "<|endoftext|>"' in text
    assert "TEMPLATE" not in crea_mycode.modelfile("qwen2.5-coder:7b", with_template=False)


def test_find_gguf_prefers_q4_k_m(tmp_path, monkeypatch):
    gguf = tmp_path / "outputs" / "gguf"
    gguf.mkdir(parents=True)
    (gguf / "unsloth.F16.gguf").write_bytes(b"x" * 20)
    (gguf / "unsloth.Q4_K_M.gguf").write_bytes(b"x" * 10)
    monkeypatch.setattr(crea_mycode, "HERE", tmp_path)
    assert crea_mycode.find_gguf(None).name == "unsloth.Q4_K_M.gguf"


def test_mycode_is_created_locally_not_pulled(settings, tmp_path):
    assert health.local_model_hint("mycode:latest") and health.local_model_hint("qwen2.5-coder:7b") is None
    req = httpx.Request("POST", "http://localhost:11434/v1/chat/completions")
    err = openai.NotFoundError("Error code: 404 - {'error': {'message': \"model 'mycode' not found\"}}",
                               response=httpx.Response(404, request=req), body=None)
    title, hint = health.explain_error(err, settings)
    assert "mycode non è installato" in title and "crea_mycode.py" in hint

    console = Console(record=True, width=160, force_terminal=False, color_system=None)
    with create_pipe_input() as pipe:
        app = TuiApp(Orchestrator(settings, llm=FakeLLM()), console=console, prompt_input=pipe,
                     prompt_output=DummyOutput(), ask=lambda q: "1", root=tmp_path, background=False)
        pulled = []
        app.pull_models = lambda models: pulled.append(models) or True
        app.handle_command("/pull mycode qwen2.5-coder:1.5b")
    assert pulled == [["qwen2.5-coder:1.5b"]] and "mycode non si scarica" in console.export_text()
