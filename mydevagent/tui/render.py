"""Rendering stile Claude Code: righe ⏺/⎿ per agenti e tool, spinner, Markdown in streaming."""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.markdown import Markdown
from rich.spinner import Spinner
from rich.text import Text

ACCENT = "#d97757"


def split_complete(text: str) -> tuple[str, str]:
    """Divide il testo in (blocchi completi, coda in corso) all'ultima riga vuota fuori dai blocchi di codice.

    I blocchi completi vengono stampati definitivamente nello scrollback; solo la coda resta nella zona
    animata, così anche risposte lunghe non sforano l'altezza del terminale.
    """
    idx = text.rfind("\n\n")
    while idx > 0:
        if text[:idx].count("```") % 2 == 0:
            return text[: idx + 2], text[idx + 2 :]
        idx = text.rfind("\n\n", 0, idx)
    return "", text


def short_args(args: dict[str, Any], limit: int = 60) -> str:
    parts = []
    for key, value in args.items():
        value = str(value).replace("\n", " ")
        parts.append(f'{key}="{value[:40]}…"' if len(value) > 40 else f'{key}="{value}"')
    joined = ", ".join(parts)
    return joined if len(joined) <= limit else joined[: limit - 1] + "…"


class TurnRenderer:
    """Riceve eventi e chunk dall'orchestratore e li disegna. Tutti i metodi girano nel thread della UI."""

    def __init__(self, console: Console, names: dict[str, str]) -> None:
        self.console = console
        self.names = names  # chiave agente → nome leggibile
        self.status = "Sto ragionando"
        self.started = time.monotonic()
        self.tail = ""
        self.answer = ""
        self.tokens = 0
        self.summary = ""
        self.cancelled = False

    # ------------------------------------------------------------ eventi
    def on_event(self, event: dict[str, Any]) -> None:
        kind = event["type"]
        c = self.console
        if kind == "route":
            agents = [self.names.get(a, a) for a in event["agents"] if a != "formatter"]
            if event["mode"] == "fast":
                c.print(f"[dim]⏺ fast · {agents[0] if agents else ''}[/]")
            else:
                c.print(f"[{ACCENT}]⏺[/] [bold]Team {event['mode']}[/] [dim]· {len(event['agents'])} agenti[/]")
                c.print(f"  [dim]⎿  {' → '.join(agents)} → Formatter[/]")
        elif kind == "agent_start":
            self.status = f"{event.get('name', event['agent'])} sta lavorando"
            if event["agent"] == "formatter":
                self.status = "Scrivo la risposta"
        elif kind == "agent_end" and event["agent"] != "final":
            tokens = event.get("prompt_tokens", 0) + event.get("completion_tokens", 0)
            self.tokens += tokens
            name = event.get("name", event["agent"])
            if event.get("error"):
                c.print(f"[red]⏺[/] [bold]{name}[/]\n  [red]⎿  {event['error']}[/]")
            else:
                tools = f" · {event['tool_calls']} tool" if event.get("tool_calls") else ""
                c.print(f"[green]⏺[/] [bold]{name}[/]\n  [dim]⎿  {event['ms'] / 1000:.1f}s · {tokens} tok{tools}[/]")
        elif kind == "tool_call":
            c.print(f"  [{ACCENT}]⏺[/] {event['tool']}([dim]{short_args(event.get('args', {}))}[/])")
        elif kind == "tool_result":
            first = (event.get("preview") or "").strip().splitlines()[:1]
            color = "dim" if event.get("ok") else "red"
            c.print(f"    [{color}]⎿  {(first[0] if first else 'ok')[:100]}[/]")
        elif kind == "info":
            c.print(f"  [dim]⎿  {event['text']}[/]")
        elif kind == "cancelled":
            self.cancelled = True
        elif kind == "done":
            self.summary = event.get("summary", "")

    def on_chunk(self, text: str) -> None:
        if self.cancelled:
            return
        if not self.answer:
            self.console.print()
        self.answer += text
        self.tail += text
        done, self.tail = split_complete(self.tail)
        if done.strip():
            self.console.print(Markdown(done))

    # ------------------------------------------------------------- vista
    def view(self) -> RenderableType:
        elapsed = time.monotonic() - self.started
        spinner = Spinner(
            "dots",
            text=Text.from_markup(f"[{ACCENT}]✻ {self.status}…[/] [dim](Ctrl+C per interrompere · "
                                  f"{elapsed:.0f}s · {self.tokens + len(self.answer) // 4} tok)[/]"),
            style=ACCENT,
        )
        if self.tail.strip():
            return Group(Markdown(self.tail), Text(""), spinner)
        return spinner

    def finish(self) -> None:
        if self.tail.strip():
            self.console.print(Markdown(self.tail))
        self.tail = ""
        if self.cancelled:
            self.console.print("[yellow]⏺ Interrotto dall'utente[/]")
        if self.summary:
            self.console.print(f"[dim]{self.summary}[/]")
