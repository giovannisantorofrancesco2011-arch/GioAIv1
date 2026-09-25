"""Rendering stile Claude Code: righe ⏺/⎿ per agenti e tool, diff, todo, spinner, Markdown in streaming."""

from __future__ import annotations

import time
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.markdown import Markdown
from rich.markup import escape
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from . import mascot

ACCENT = mascot.PURPLE
THEMES = {
    "dark": {"code": "monokai", "diff": "ansi_dark"},
    "light": {"code": "friendly", "diff": "ansi_light"},
}
THEME = dict(THEMES["dark"])
MAX_DIFF_LINES = 40
TOOL_LABELS = {
    "read_file": "Read", "list_files": "List", "grep": "Search", "bash": "Bash", "run_tests": "Test",
    "web_search": "Web", "web_fetch": "Fetch", "rag_search": "Codebase", "skill": "Skill", "mcp": "MCP",
    "task": "Agent",
}
TODO_ICONS = {"completed": "[green]☑[/]", "in_progress": f"[{ACCENT}]◼[/]", "pending": "[dim]☐[/]"}


def set_theme(name: str) -> None:
    THEME.update(THEMES.get(name, THEMES["dark"]))


def markdown(text: str) -> Markdown:
    return Markdown(text, code_theme=THEME["code"])


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


def short_args(args: dict[str, Any], limit: int = 70) -> str:
    if len(args) == 1:  # un solo argomento: mostra il valore, come Claude Code → Read(src/app.py)
        value = str(next(iter(args.values()))).replace("\n", " ")
        return value if len(value) <= limit else value[: limit - 1] + "…"
    parts = []
    for key, value in args.items():
        value = str(value).replace("\n", " ")
        parts.append(f'{key}="{value[:40]}…"' if len(value) > 40 else f'{key}="{value}"')
    joined = ", ".join(parts)
    return joined if len(joined) <= limit else joined[: limit - 1] + "…"


def render_diff(diff: str, max_lines: int = MAX_DIFF_LINES) -> RenderableType:
    lines = [line for line in diff.splitlines() if not line.startswith(("---", "+++"))]
    extra = len(lines) - max_lines
    body = "\n".join(lines[:max_lines]) + (f"\n… altre {extra} righe (/diff per vederle tutte)" if extra > 0 else "")
    return Syntax(body, "diff", theme=THEME["diff"], word_wrap=True, background_color="default")


def render_todos(todos: list[dict[str, str]]) -> str:
    return "\n".join(f"     {TODO_ICONS.get(t['status'], '☐')} "
                     + (f"[strike dim]{escape(t['content'])}[/]" if t["status"] == "completed"
                        else escape(t["content"])) for t in todos)


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
        self.todos: list[dict[str, str]] = []
        self.shown_diffs: set[str] = set()  # diff già mostrati nella richiesta di conferma
        self.step = 0

    # ------------------------------------------------------------ eventi
    def on_event(self, event: dict[str, Any]) -> None:
        kind = event["type"]
        c = self.console
        if kind == "route":
            agents = [self.names.get(a, a) for a in event["agents"] if a != "formatter"]
            suffix = " · agente" if event.get("agentic") else ""
            if event["mode"] == "ultra-deep":
                c.print(f"[{ACCENT}]⏺[/] [bold]Team ultra-deep[/][dim]{suffix} · 35 agenti · ricerca web se serve[/]")
            elif event["mode"] == "fast":
                c.print(f"[dim]⏺ fast{suffix} · {agents[0] if agents else ''}[/]")
            else:
                c.print(f"[{ACCENT}]⏺[/] [bold]Team {event['mode']}[/][dim]{suffix} · {len(agents)} agenti[/]")
                c.print(f"  [dim]⎿  {' → '.join(agents)}[/]")
            if event.get("suggest_ultra"):
                c.print("  [dim]⎿  suggerimento: per un lavoro di questa portata prova [bold]/ultra-deep[/] (35 agenti)[/]")
        elif kind == "agent_start":
            self.status = f"{event.get('name', event['agent'])} sta lavorando"
            if event["agent"] == "formatter":
                self.status = "Scrivo la risposta"
        elif kind == "agent_end" and event["agent"] != "final":
            tokens = event.get("prompt_tokens", 0) + event.get("completion_tokens", 0)
            if not event.get("quiet"):
                self.tokens += tokens
            name = event.get("name", event["agent"])
            if event.get("error"):
                c.print(f"[red]⏺[/] [bold]{name}[/]\n  [red]⎿  {escape(str(event['error']))}[/]")
            elif not event.get("quiet"):
                tools = f" · {event['tool_calls']} tool" if event.get("tool_calls") else ""
                c.print(f"[green]⏺[/] [bold]{name}[/]\n  [dim]⎿  {event['ms'] / 1000:.1f}s · {tokens} tok{tools}[/]")
        elif kind == "agent_skip":
            c.print(f"[dim]⏺ {escape(event['name'])}\n  ⎿  {escape(event['reason'])}[/]")
        elif kind == "agent_step":
            self.step = event["step"]
            self.status = f"Sto lavorando (passo {self.step})"
        elif kind == "llm_call":
            self.tokens += event.get("prompt_tokens", 0) + event.get("completion_tokens", 0)
        elif kind == "agent_text":
            c.print(f"[white]⏺[/] {escape(event['text'].strip())}")
        elif kind == "tool_call":
            if event["tool"] in ("edit_file", "write_file", "todo_write"):
                return  # mostrati dagli eventi diff/todo
            label = TOOL_LABELS.get(event["tool"], event["tool"])
            c.print(f"[{ACCENT}]⏺[/] [bold]{label}[/]([dim]{escape(short_args(event.get('args', {})))}[/])")
            self.status = f"{label}…"
        elif kind == "tool_result":
            if event["tool"] in ("todo_write",) or (event["tool"] in ("edit_file", "write_file") and event.get("ok")):
                return
            first = (event.get("preview") or "").strip().splitlines()[:1]
            color = "dim" if event.get("ok") else "red"
            c.print(f"  [{color}]⎿  {escape((first[0] if first else 'ok')[:110])}[/]")
        elif kind == "diff":
            c.print(f"[{ACCENT}]⏺[/] [bold]{event['action']}[/]([cyan]{escape(event['path'])}[/])")
            c.print(f"  [dim]⎿  [green]+{event['added']}[/] [red]−{event['removed']}[/][/]")
            if event["path"] not in self.shown_diffs and event.get("diff"):
                c.print(render_diff(event["diff"]))
            self.shown_diffs.discard(event["path"])
        elif kind == "todo":
            self.todos = event["todos"]
            done = sum(t["status"] == "completed" for t in self.todos)
            c.print(f"[{ACCENT}]⏺[/] [bold]Todo[/] [dim]({done}/{len(self.todos)})[/]")
            c.print(render_todos(self.todos))
        elif kind == "tests":
            c.print(f"  {'[green]⎿  ✓ test passati' if event['ok'] else '[red]⎿  ✗ test falliti'}[/]")
        elif kind == "info":
            if event["text"].startswith("fase "):
                c.print(f"[{ACCENT}]✻[/] [bold]{escape(event['text'])}[/]")
                self.status = event["text"]
            else:
                c.print(f"  [dim]⎿  {escape(event['text'])}[/]")
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
            self.console.print(markdown(done))

    # ------------------------------------------------------------- vista
    def view(self) -> RenderableType:
        elapsed = time.monotonic() - self.started
        status = Text.from_markup(
            f"\n[{ACCENT}]{escape(self.status)}…[/]\n[dim]esc per interrompere · {elapsed:.0f}s · "
            f"{self.tokens + len(self.answer) // 4:,} tok[/]".replace(",", "."))
        working = Table.grid(padding=(0, 2))
        working.add_column(no_wrap=True)
        working.add_column()
        # Vio lavora: si guarda intorno e muove i tentacoli
        working.add_row(mascot.render("think" if int(elapsed) % 4 else "look", int(elapsed * 2)), status)
        parts: list[RenderableType] = []
        if self.tail.strip():
            parts += [markdown(self.tail), Text("")]
        active = [t for t in self.todos if t["status"] != "completed"]
        if active:
            parts.append(Text.from_markup(render_todos(self.todos)))
        parts.append(working)
        return Group(*parts)

    def finish(self) -> None:
        if self.tail.strip():
            self.console.print(markdown(self.tail))
        self.tail = ""
        if self.cancelled:
            self.console.print("[yellow]⏺ Interrotto dall'utente[/]")
        if self.summary:
            self.console.print(f"[{ACCENT}]✻[/] [dim]{escape(self.summary)}[/]")
