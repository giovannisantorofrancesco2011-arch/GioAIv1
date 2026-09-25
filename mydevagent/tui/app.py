"""UI da terminale stile Claude Code per MyDevAgent.

Architettura:
  - thread principale: input (prompt_toolkit) e disegno (rich.Live)
  - thread worker: Orchestrator.run(); comunica solo tramite una queue.Queue di eventi/chunk
  - Ctrl+C durante una risposta imposta un threading.Event → l'orchestratore si ferma
"""

from __future__ import annotations

import queue
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from ..config import load_settings
from ..orchestrator import Orchestrator
from ..tools.filesystem import Workspace
from .apply import apply_answer
from .completion import DevCompleter
from .render import ACCENT, TurnRenderer
from .session import Session, list_sessions, state_dir

COMMANDS = {
    "/help": "mostra comandi e scorciatoie",
    "/fast": "modalità veloce (1 agente)",
    "/balanced": "team standard con test e review",
    "/deep": "team completo: security, performance, edge case, docs",
    "/auto": "modalità scelta dal router (default)",
    "/apply": "scrivi su disco i file dell'ultima risposta (con diff e conferma)",
    "/agents": "elenca i 15 agenti",
    "/files": "file allegati all'ultimo messaggio",
    "/cost": "token e tempo della sessione",
    "/think": "mostra/nascondi il ragionamento del modello",
    "/index": "indicizza il progetto per il RAG",
    "/resume": "riprendi una sessione precedente in questa cartella",
    "/export": "salva la conversazione in Markdown",
    "/clear": "nuova conversazione",
    "/exit": "esci",
}
MODES = ("auto", "fast", "balanced", "deep")
SHELL_TIMEOUT = 120
MAX_SHELL_OUTPUT = 8000


class TuiApp:
    def __init__(
        self,
        orchestrator: Orchestrator | None = None,
        *,
        profile: str | None = None,
        console: Console | None = None,
        prompt_input=None,
        prompt_output=None,
        ask: Callable[[str], str] | None = None,
        session: Session | None = None,
        root: Path | None = None,
    ) -> None:
        self.orch = orchestrator or Orchestrator(load_settings(overrides={"profile": profile} if profile else None))
        self.console = console or Console()
        self.root = (root or Path.cwd()).resolve()
        self.session = session or Session(cwd=str(self.root))
        self.mode = self.session.mode
        self.show_thinking = False
        self.last_answer = next((m["content"] for m in reversed(self.session.history)
                                 if m["role"] == "assistant"), "")
        self.last_files: dict[str, str] = {}
        self.pending_context: dict[str, str] = {}  # output di comandi `!` da allegare al prossimo turno
        self.stats = {"tokens": 0, "turns": 0, "seconds": 0.0}
        self.names = {a.key: a.name for a in self.orch.registry}
        self.model = self.orch.settings.resolve_model("main")[0]
        self.online: bool | None = None
        self.branch = self._git_branch()
        self._ask = ask
        self._ctrl_c_at = 0.0
        self.completer = DevCompleter(COMMANDS, dict(self.orch.registry.by_alias), self.root)
        self.prompt = self._build_prompt(prompt_input, prompt_output)
        threading.Thread(target=self._check_online, daemon=True).start()

    # ------------------------------------------------------------ setup
    def _build_prompt(self, prompt_input, prompt_output) -> PromptSession:
        keys = KeyBindings()

        @keys.add("escape", "enter")  # Alt+Enter → nuova riga
        def _newline(event) -> None:
            event.current_buffer.insert_text("\n")

        @keys.add("c-j")  # Ctrl+J → nuova riga (funziona in ogni terminale)
        def _newline2(event) -> None:
            event.current_buffer.insert_text("\n")

        try:
            history = FileHistory(str(state_dir() / "history"))
        except OSError:
            history = InMemoryHistory()
        return PromptSession(
            history=history,
            completer=self.completer,
            complete_while_typing=True,
            key_bindings=keys,
            bottom_toolbar=self.toolbar,
            placeholder=[("class:placeholder", "Chiedi qualcosa… / comandi · @ file e agenti · ! shell")],
            style=_style(),
            input=prompt_input,
            output=prompt_output,
        )

    def _check_online(self) -> None:
        try:
            self.online = self.orch.toolbox.ctx.connectivity.online()
        except Exception:
            self.online = False

    def _git_branch(self) -> str:
        try:
            out = subprocess.run(["git", "-C", str(self.root), "rev-parse", "--abbrev-ref", "HEAD"],
                                 capture_output=True, text=True, timeout=3)
            return out.stdout.strip() if out.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            return ""

    # ------------------------------------------------------------- vista
    def toolbar(self):
        net = {True: ("class:tb.ok", "● online"), False: ("class:tb.warn", "○ offline"),
               None: ("class:tb.dim", "… rete")}[self.online]
        parts = [
            ("class:tb.key", f" {self.orch.settings.profile} "), ("class:tb", f" {self.model} "),
            ("class:tb.dim", "· modo "), ("class:tb.key", self.mode), ("class:tb.dim", " · "), net,
            ("class:tb.dim", f" · ~{self.stats['tokens']:,} tok".replace(",", ".")),
        ]
        if self.branch:
            parts.append(("class:tb.dim", f" ·  {self.branch}"))
        return parts

    def banner(self) -> None:
        profile = self.orch.settings.profile
        body = (
            f"[bold {ACCENT}]✻[/] [bold]Benvenuto in MyDevAgent[/]  [dim]15 agenti · local-first[/]\n\n"
            f"[dim]cwd:[/]     {escape(str(self.root))}\n"
            f"[dim]profilo:[/] {profile} · [dim]modello:[/] {self.model}\n\n"
            "[dim]Suggerimenti:[/]\n"
            "  [dim]•[/] [bold]/[/] comandi · [bold]@file[/] allega · [bold]@security @perf @web[/] coinvolgi agenti\n"
            "  [dim]•[/] [bold]![/]comando esegue la shell (es. [bold]!pytest[/]) e ne allega l'output\n"
            "  [dim]•[/] [bold]/apply[/] salva i file generati · [bold]Alt+Enter[/] nuova riga · "
            "[bold]Ctrl+C[/] interrompe"
        )
        self.console.print(Panel(body, border_style=ACCENT, expand=False, padding=(0, 2)))
        if self.session.history:
            turns = len(self.session.history) // 2
            self.console.print(f"[dim]⎿  Ripresa sessione «{escape(self.session.title)}» ({turns} turni)[/]")

    # ----------------------------------------------------------- comandi
    def ask(self, question: str) -> str:
        if self._ask:
            return self._ask(question)
        self.console.print(f"[bold]{escape(question)}[/]  [dim]1[/] Sì  [dim]2[/] Sì, a tutti  [dim]3[/] No")
        answer = self.prompt.prompt("  › ", bottom_toolbar=None, completer=None, placeholder="").strip()
        return answer if answer in ("1", "2", "3") else "3"

    def handle_command(self, text: str) -> bool:
        """Esegue un comando `/`. Restituisce False per uscire."""
        cmd, _, arg = text.partition(" ")
        cmd = cmd.lower()
        c = self.console
        if cmd in ("/exit", "/quit"):
            return False
        if cmd == "/help":
            table = Table(show_header=False, box=None, padding=(0, 2))
            for name, desc in COMMANDS.items():
                table.add_row(f"[bold]{name}[/]", f"[dim]{desc}[/]")
            c.print(table)
            c.print("[dim]Scorciatoie: Tab completa · ↑/↓ cronologia · Alt+Enter o Ctrl+J nuova riga · "
                    "Ctrl+C interrompe/pulisce · Ctrl+D esce[/]")
        elif cmd[1:] in MODES and not arg:
            self.mode = self.session.mode = cmd[1:]
            c.print(f"[dim]⎿  modalità: {self.mode}[/]")
        elif cmd in ("/fast", "/balanced", "/deep") and arg:
            self.submit(text)  # "/deep crea un'API" → il router gestisce il comando inline
        elif cmd == "/apply":
            if not self.last_answer:
                c.print("[dim]⎿  Nessuna risposta da applicare.[/]")
            else:
                written = apply_answer(self.last_answer, self.orch.registry, self.root, c, self.ask)
                if written:
                    self.completer.refresh()
        elif cmd == "/agents":
            table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
            for col in ("#", "agente", "stage", "alias"):
                table.add_column(col)
            for a in self.orch.registry:
                table.add_row(str(a.id), a.name, a.stage, " ".join("@" + x for x in a.aliases))
            c.print(table)
        elif cmd == "/files":
            c.print("[dim]⎿  " + (", ".join(self.last_files) or "nessun file allegato") + "[/]")
        elif cmd == "/cost":
            c.print(f"[dim]⎿  {self.stats['turns']} turni · ~{self.stats['tokens']:,} token · "
                    f"{self.stats['seconds']:.0f}s di lavoro degli agenti[/]".replace(",", "."))
        elif cmd == "/think":
            self.show_thinking = not self.show_thinking
            c.print(f"[dim]⎿  mostra ragionamento: {'sì' if self.show_thinking else 'no'}[/]")
        elif cmd == "/index":
            self._index()
        elif cmd == "/resume":
            self._resume()
        elif cmd == "/export":
            path = self.root / f"mydevagent-{self.session.id}.md"
            path.write_text(self.session.to_markdown(), encoding="utf-8")
            c.print(f"[dim]⎿  salvata in {escape(str(path))}[/]")
        elif cmd == "/clear":
            self.session = Session(cwd=str(self.root), mode=self.mode)
            self.last_answer, self.last_files, self.pending_context = "", {}, {}
            c.clear()
            self.banner()
        else:
            c.print(f"[red]⎿  comando sconosciuto: {escape(cmd)}[/] [dim](/help)[/]")
        return True

    def _index(self) -> None:
        from ..tools.rag import CodeIndex

        settings = self.orch.settings.model_copy(deep=True)
        settings.tools.filesystem.root = str(self.root)
        index = CodeIndex.for_workspace(settings, self.orch.llm)
        with self.console.status(f"[{ACCENT}]✻ Indicizzo il progetto…[/]"):
            stats = index.build()
        self.orch.toolbox.ctx.cache.pop("index", None)
        kind = "semantico" if stats["embedded"] else "lessicale"
        self.console.print(f"[green]⏺[/] Indice {kind}: {stats['chunks']} blocchi\n  [dim]⎿  {index.path}[/]")

    def _resume(self) -> None:
        sessions = [s for s in list_sessions(str(self.root)) if s.id != self.session.id]
        if not sessions:
            self.console.print("[dim]⎿  Nessuna sessione precedente in questa cartella.[/]")
            return
        for i, s in enumerate(sessions, start=1):
            when = time.strftime("%d/%m %H:%M", time.localtime(s.updated))
            self.console.print(f"  [bold]{i}[/] [dim]{when}[/] {escape(s.title)} [dim]({len(s.history) // 2} turni)[/]")
        choice = self.prompt.prompt("  numero › ", bottom_toolbar=None, completer=None, placeholder="").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(sessions):
            self.session = sessions[int(choice) - 1]
            self.mode = self.session.mode
            self.last_answer = next((m["content"] for m in reversed(self.session.history)
                                     if m["role"] == "assistant"), "")
            self.console.print(f"[dim]⎿  Ripresa «{escape(self.session.title)}»[/]")

    # ------------------------------------------------------------- shell
    def run_shell(self, command: str) -> None:
        """`!comando`: esegue nella cartella del progetto e allega l'output al prossimo messaggio."""
        self.console.print(f"[{ACCENT}]⏺[/] Bash([bold]{escape(command)}[/])")
        try:
            proc = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True,
                                  timeout=SHELL_TIMEOUT)
            output, code = (proc.stdout + proc.stderr).strip(), proc.returncode
        except subprocess.TimeoutExpired:
            output, code = f"timeout dopo {SHELL_TIMEOUT}s", -1
        lines = output.splitlines()
        shown = lines[:15]
        for i, line in enumerate(shown):
            prefix = "  ⎿  " if i == 0 else "     "
            self.console.print(f"[dim]{prefix}{escape(line[:200])}[/]")
        if len(lines) > len(shown):
            self.console.print(f"[dim]     … altre {len(lines) - len(shown)} righe[/]")
        status = "[green]exit 0[/]" if code == 0 else f"[red]exit {code}[/]"
        self.console.print(f"     {status} [dim]· output allegato al prossimo messaggio[/]")
        self.pending_context[f"$ {command}"] = f"exit code {code}\n{output[-MAX_SHELL_OUTPUT:]}"

    # -------------------------------------------------------------- turni
    def collect_attachments(self, text: str) -> dict[str, str]:
        files: dict[str, str] = {}
        for token in text.split():
            if not token.startswith("@") or len(token) < 2:
                continue
            candidate = token[1:].rstrip(",.;:")
            try:
                path = (self.root / candidate).resolve()
            except OSError:
                continue
            if path.is_file() and path.is_relative_to(self.root) and not Workspace.is_secret(path):
                files[candidate] = path.read_text(encoding="utf-8", errors="replace")
        return files

    def submit(self, text: str) -> str:
        files = self.collect_attachments(text)
        for name in files:
            self.console.print(f"  [dim]⎿  allegato {escape(name)}[/]")
        files.update(self.pending_context)
        self.pending_context = {}
        self.last_files = files
        answer = self.run_turn(text, files)
        self.session.add_turn(text, answer)
        return answer

    def run_turn(self, text: str, files: dict[str, str]) -> str:
        events: queue.Queue = queue.Queue()
        cancel = threading.Event()
        renderer = TurnRenderer(self.console, self.names)
        started = time.monotonic()

        def worker() -> None:
            try:
                for chunk in self.orch.run(text, history=self.session.history, files=files,
                                           mode=None if self.mode == "auto" else self.mode,
                                           on_event=lambda e: events.put(("event", e)),
                                           show_thinking=self.show_thinking, cancel=cancel):
                    events.put(("chunk", chunk))
            except Exception as exc:
                events.put(("error", f"{type(exc).__name__}: {exc}"))
            finally:
                events.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()
        abandoned = False
        with Live(renderer.view(), console=self.console, refresh_per_second=12, transient=True) as live:
            while True:
                try:
                    try:
                        kind, value = events.get(timeout=0.08)
                    except queue.Empty:
                        live.update(renderer.view())
                        continue
                    if kind == "done":
                        break
                    if kind == "error":
                        self.console.print(f"[red]⏺ Errore: {escape(value)}[/]\n  [dim]⎿  prova /help o "
                                           "`mydevagent doctor`[/]")
                    elif kind == "chunk":
                        renderer.on_chunk(value)
                    else:
                        renderer.on_event(value)
                    live.update(renderer.view())
                except KeyboardInterrupt:
                    if cancel.is_set():  # secondo Ctrl+C: abbandona senza aspettare l'agente corrente
                        abandoned = True
                        break
                    cancel.set()
                    renderer.cancelled = True
                    renderer.status = "Interrompo (Ctrl+C di nuovo per forzare)"
            live.update("")
        renderer.finish()
        if abandoned:
            self.console.print("[dim]  ⎿  l'agente in corso terminerà in background[/]")
        elapsed = time.monotonic() - started
        self.stats["turns"] += 1
        self.stats["seconds"] += elapsed
        self.stats["tokens"] += self.orch.last_run.tokens or renderer.tokens
        answer = renderer.answer + ("\n\n[interrotto]" if renderer.cancelled else "")
        self.last_answer = renderer.answer
        return answer

    # --------------------------------------------------------------- loop
    def loop(self) -> None:
        self.banner()
        while True:
            self.console.print()
            try:
                text = self.prompt.prompt([("class:prompt", "> ")]).strip()
            except KeyboardInterrupt:
                now = time.monotonic()
                if now - self._ctrl_c_at < 1.5:
                    break
                self._ctrl_c_at = now
                self.console.print("[dim]⎿  Ctrl+C di nuovo per uscire[/]")
                continue
            except EOFError:
                break
            if not text:
                continue
            if text.startswith("!"):
                if text[1:].strip():
                    self.run_shell(text[1:].strip())
                continue
            if text.startswith("/") and not text.startswith("//"):
                if not self.handle_command(text):
                    break
                continue
            self.submit(text)
        self.session.save()
        self.console.print(f"[dim]Sessione salvata: {self.session.id} · riprendi con `mydevagent --continue`[/]")


def _style():
    from prompt_toolkit.styles import Style

    return Style.from_dict({
        "prompt": f"bold {ACCENT}",
        "placeholder": "#7a7a7a italic",
        "bottom-toolbar": "noreverse bg:default #9a9a9a",
        "tb": "#c0c0c0",
        "tb.key": f"bold {ACCENT}",
        "tb.dim": "#7a7a7a",
        "tb.ok": "#6fbf73",
        "tb.warn": "#e0b04a",
        "completion-menu.completion": "bg:#2b2b2b #d0d0d0",
        "completion-menu.completion.current": f"bg:{ACCENT} #ffffff",
        "completion-menu.meta.completion": "bg:#2b2b2b #8a8a8a",
        "completion-menu.meta.completion.current": f"bg:{ACCENT} #ffffff",
    })


def run_tui(profile: str | None = None, continue_last: bool = False) -> None:
    session = None
    if continue_last:
        previous = list_sessions(str(Path.cwd().resolve()), limit=1)
        session = previous[0] if previous else None
    TuiApp(profile=profile, session=session).loop()
