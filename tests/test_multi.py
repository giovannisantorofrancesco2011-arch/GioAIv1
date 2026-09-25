import functools
import json
import threading
import time

import httpx
import pytest
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.output import DummyOutput
from rich.console import Console
from rich.markdown import Markdown

from mydevagent.orchestrator import Orchestrator
from mydevagent.tui import multi
from mydevagent.tui.app import TuiApp
from tests.test_agent import ScriptedLLM, T


@pytest.fixture
def room():
    room = multi.Room("gio", port=0, bind="127.0.0.1")
    yield room
    room.close()


def at(room, path):
    return f"http://127.0.0.1:{room.port}{path}"


def next_item(lines):
    return next(json.loads(line[6:]) for line in lines if line.startswith("data: "))


def test_page_and_wrong_codes(room):
    assert "Entra nella sessione" in httpx.get(at(room, "/")).text
    assert httpx.get(at(room, "/events?codice=NOPE22")).status_code == 403
    assert httpx.post(at(room, "/send"), json={"codice": "x", "nome": "M", "testo": "ciao"}).status_code == 403
    for _ in range(multi.MAX_FAILURES):
        httpx.post(at(room, "/join"), json={"codice": "sbagliato"})
    assert httpx.post(at(room, "/join"), json={"codice": room.code}).status_code == 429  # ora nemmeno quello giusto
    assert room.inbox.empty() and not room.guests


def test_guests_join_and_write(room):
    woke = threading.Event()
    room.on_message = woke.set
    joined = httpx.post(at(room, "/join"), json={"codice": room.code.lower(), "nome": "GIO"}).json()
    assert joined == {"host": "gio", "nome": "GIO (ospite)"}  # non può spacciarsi per l'host
    sent = httpx.post(at(room, "/send"), json={"codice": room.code, "nome": "<b>Marco</b>", "testo": " fai il bottone blu "})
    assert sent.status_code == 200 and woke.is_set()
    assert room.next_message() == ("bMarcob", "fai il bottone blu") and room.next_message() is None
    assert ("system", "bMarcob si è collegato") in [(i["kind"], i.get("text")) for i in room.feed]
    assert room.guests == ["GIO (ospite)", "bMarcob"]


def test_events_stream_and_resume(room):
    room.system("uno")
    with httpx.stream("GET", at(room, f"/events?codice={room.code}"), timeout=5) as response:
        lines = response.iter_lines()
        assert next_item(lines)["text"] == "uno"
        room.publish({"kind": "busy", "on": True})
        assert next_item(lines) == {"kind": "busy", "on": True, "id": 1}
    headers = {"Last-Event-ID": "0"}  # il browser si ricollega: riparte da dov'era
    with httpx.stream("GET", at(room, f"/events?codice={room.code}"), headers=headers, timeout=5) as response:
        assert next_item(response.iter_lines())["id"] == 1


def test_html_is_escaped_and_has_no_links():
    console = Console(file=multi._Nowhere(), record=True, width=60, force_terminal=True, color_system="truecolor")
    console.print("<b>ciao</b>", markup=False, highlight=False)
    console.print(Markdown('[clic](https://x.y/"onmouseover="alert(1))'), "[red]rosso[/]")
    html = multi.to_html(console)
    assert "&lt;b&gt;ciao&lt;/b&gt;" in html and "<b>" not in html
    assert "<a" not in html and "onmouseover" not in html and "clic" in html
    assert '<span style="color: #' in html  # i colori del terminale
    assert multi.to_html(console) == ""  # quello che è già partito non si rimanda


def make_app(settings, tmp_path, monkeypatch, llm, **kwargs):
    monkeypatch.setattr(multi, "Room", functools.partial(multi.Room, port=0, bind="127.0.0.1"))
    project = tmp_path / "proj"
    project.mkdir()
    app = TuiApp(Orchestrator(settings, llm=llm), console=Console(record=True, width=100), prompt_output=DummyOutput(),
                 root=project, background=False, **kwargs)
    app.mode = "fast"
    app.handle_command("/multi")
    return app, project


def test_guest_turn_needs_the_host_ok(settings, tmp_path, monkeypatch):
    llm = ScriptedLLM(steps=[T("write_file", path="blu.css", content="button { color: blue }\n"), "Bottone blu fatto!"])
    questions = []
    with create_pipe_input() as pipe:
        app, project = make_app(settings, tmp_path, monkeypatch, llm, prompt_input=pipe, permission_mode="auto",
                                ask=lambda q: questions.append(q) or "1")
        room = app.room
        assert "?codice=" + room.code in app.console.export_text(clear=False)
        room.message("Marco", "fai il bottone blu")
        pipe.send_text("/exit\r")
        app.loop()
    assert questions == ["Applicare la modifica a blu.css?"]  # in modalità auto, ma l'ha chiesto un amico
    assert app.policy.mode == "auto" and (project / "blu.css").is_file()
    assert "Marco: fai il bottone blu" in llm.calls[0]["messages"][-1]["content"]
    assert app.session.history[0]["content"] == "Marco: fai il bottone blu"
    assert "› Marco: fai il bottone blu" in app.console.export_text()
    shared = "".join(i["html"] for i in room.feed if i["kind"] == "html")
    assert "deve confermare…" in shared and "button { color: blue }" in shared and "Bottone blu fatto!" in shared
    busy = [i["on"] for i in room.feed if i["kind"] == "busy"]
    assert busy == [True, False] and room.closed


def test_guest_message_wakes_the_prompt(settings, tmp_path, monkeypatch):
    llm = ScriptedLLM(steps=["Ciao Marco!", "Ok, finisco la frase."])
    with create_pipe_input() as pipe:
        app, _ = make_app(settings, tmp_path, monkeypatch, llm, prompt_input=pipe)
        room = app.room

        def friend():
            deadline = time.monotonic() + 20
            while not app.prompt.app.is_running and time.monotonic() < deadline:
                time.sleep(0.05)
            time.sleep(0.3)
            pipe.send_text("mezza frase")  # l'host sta scrivendo…
            time.sleep(0.3)
            httpx.post(at(room, "/send"), json={"codice": room.code, "nome": "Marco", "testo": "ciao"})
            while not any(i["kind"] == "busy" and not i["on"] for i in room.feed) and time.monotonic() < deadline:
                time.sleep(0.05)
            pipe.send_text("\r")  # …e poi finisce la sua frase, che era rimasta lì
            pipe.send_text("\x15/exit\r")

        helper = threading.Thread(target=friend, daemon=True)
        helper.start()
        app.loop()
        helper.join(5)
    assert [m["content"] for m in app.session.history if m["role"] == "user"] == ["Marco: ciao", "mezza frase"]
    assert [i["text"] for i in room.feed if i["kind"] == "message"] == ["ciao", "mezza frase"]
