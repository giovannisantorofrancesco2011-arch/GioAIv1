import json
import time
from collections import Counter
from datetime import date, datetime, timedelta

from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from mydevagent import stats
from mydevagent.orchestrator import Orchestrator
from mydevagent.tui.app import TuiApp
from mydevagent.tui.statsview import heatmap, level, render
from tests.test_agent import ScriptedLLM, T


def at(day: date, hour: int = 10) -> float:
    return datetime(day.year, day.month, day.day, hour).timestamp()


def test_turn_counts_events_once():
    turn = stats.Turn(project="/p", session="s1", model="m")
    for event in [
        {"type": "route", "mode": "fast"},
        {"type": "llm_call", "prompt_tokens": 100, "completion_tokens": 20},
        {"type": "agent_end", "agent": "lead", "prompt_tokens": 100, "completion_tokens": 20, "counted": True},
        {"type": "agent_end", "agent": "architect", "prompt_tokens": 30, "completion_tokens": 10},
        {"type": "agent_end", "agent": "final", "prompt_tokens": 999, "completion_tokens": 999},
        {"type": "tool_result", "tool": "read_file", "ok": True},
        {"type": "tool_result", "tool": "edit_file", "ok": True},
        {"type": "diff", "path": "a.py", "added": 3, "removed": 1},
        {"type": "diff", "path": "a.py", "added": 1, "removed": 0},
        {"type": "tests", "ok": False}, {"type": "tests", "ok": True},
    ]:
        turn.on_event(event)
    record = turn.finish("x" * 40, estimate=True)
    assert record["tokens"] == 120 + 40 + 10  # llm_call + architect + stima della risposta
    assert record["team"] == "fast" and record["tools"] == 2
    assert record["files"] == ["a.py"] and (record["added"], record["removed"]) == (4, 1)
    assert (record["tests_ok"], record["tests_failed"]) == (1, 1)
    assert stats.load() == [record]  # salvata in ~/.mydevagent/stats.jsonl


def test_load_skips_broken_lines_and_filters_days():
    today = date.today()
    old = {"started": at(today - timedelta(days=20)), "project": "/p", "files": ["a.py"]}
    new = {"started": at(today), "project": "/p", "files": ["a.py", "b.py"]}
    path = stats.stats_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(old) + "\n{rotta\n" + json.dumps(new) + "\n")
    assert len(stats.load()) == 2
    assert stats.load(7) == [new]
    summary = stats.summarize(stats.load())
    assert summary.turns == 2 and summary.files == 2  # file diversi per progetto


def test_streaks():
    today = date(2026, 9, 25)
    summary = stats.Summary(per_day=Counter({today - timedelta(days=d): 1 for d in (1, 2, 3, 10, 11)}))
    assert summary.streaks(today) == (3, 3)  # oggi non hai ancora scritto: la serie di ieri regge
    summary.per_day[today - timedelta(days=5)] = 1
    summary.per_day.update({today - timedelta(days=d): 1 for d in range(20, 26)})
    assert summary.streaks(today) == (3, 6)
    assert stats.Summary().streaks(today) == (0, 0)


def test_heatmap_levels_and_layout():
    assert [level(n, 8) for n in (0, 1, 2, 4, 6, 8)] == [0, 1, 1, 2, 3, 4]
    today = date(2026, 9, 25)  # un venerdì
    text = heatmap(Counter({today: 5, date(2026, 9, 1): 1}), today, weeks=8).plain
    lines = text.splitlines()
    assert "ago" in lines[0] and "set" in lines[0]
    assert lines[1].startswith(" lun ") and lines[5].startswith(" ven ")
    assert lines[5].rstrip().endswith("■")  # oggi è acceso
    assert lines[6].count("■") + lines[6].count("·") == 7  # sabato: le settimane passate, non il futuro
    assert "meno" in lines[-1] and "più" in lines[-1]


def test_render_empty_and_full():
    console = Console(record=True, width=100, color_system=None)
    console.print(render(stats.Summary(), stats.Summary()))
    assert "Ancora niente da contare" in console.export_text()
    today = date.today()
    records = [{"started": at(today - timedelta(days=d)), "project": "/home/gio/sito", "model": "qwen", "team": "fast",
                "tokens": 1500, "seconds": 90, "files": ["index.html"], "added": 10, "removed": 2, "tests_ok": 1,
                "session": f"s{d}"} for d in range(3)]
    summary = stats.summarize(records)
    console.print(render(stats.summarize(records[:1]), summary))
    out = console.export_text()
    assert "Statistiche di MyDevAgent" in out and "questa sessione" in out and "da sempre" in out
    assert "4.500" in out and "4 min" in out and "+30 −6" in out
    assert "3 giorni di fila" in out and "3 sessioni" in out
    assert "modello preferito: qwen" in out and "progetti: sito 100%" in out


def test_stats_command_in_tui(settings, tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    llm = ScriptedLLM(steps=[T("write_file", path="src/new.py", content="X = 1\nY = 2\n"), "Creato src/new.py"])
    console = Console(record=True, width=100, force_terminal=False, color_system=None)
    with create_pipe_input() as pipe:
        app = TuiApp(Orchestrator(settings, llm=llm), console=console, prompt_input=pipe,
                     prompt_output=DummyOutput(), ask=lambda q: "1", root=root, background=False)
        pipe.send_text("/fast crea src/new.py\r")
        pipe.send_text("/stats\r")
        pipe.send_text("/stats 7\r")
        pipe.send_text("/stats ieri\r")
        pipe.send_text("/exit\r")
        app.loop()
    out = console.export_text()
    assert "Statistiche di MyDevAgent" in out and "ultimi 7 giorni" in out and "uso: /stats" in out
    assert "1 giorno (il tuo record!)" in out
    [record] = stats.load()
    assert record["files"] == ["src/new.py"] and record["added"] == 2 and record["team"] == "fast"
    assert record["session"] == app.session.id and record["project"] == str(root.resolve())
    assert record["tokens"] == 30 and record["started"] <= time.time()  # 2 passi da 15 token, niente doppioni
    assert app.vio_state() == ("love", "Ecco cosa abbiamo fatto insieme!")
