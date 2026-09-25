"""UI da terminale stile Claude Code per MyDevAgent.

Architettura:
  - thread principale: input (prompt_toolkit), disegno (rich.Live), conferme dei permessi
  - thread worker: AgentRunner.run() (modalità agente) oppure Orchestrator.run() (modalità chat);
    comunica solo tramite una queue.Queue di eventi, chunk e richieste di conferma
  - Esc / Ctrl+C durante il lavoro impostano un threading.Event → il team si ferma
"""

from __future__ import annotations

import json
import queue
import subprocess
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory, InMemoryHistory
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from ..agent import CheckpointStore, PermissionPolicy
from ..agent.context import append_memory, read_memory
from ..agent.permissions import MODE_LABELS, ApprovalRequest
from ..agent.permissions import MODES as PERMISSION_MODES
from ..agent.runner import AgentRunner
from ..config import load_settings
from ..orchestrator import Orchestrator
from ..tools.filesystem import Workspace
from . import extras
from .apply import apply_answer
from .completion import DevCompleter
from .keys import EscWatcher
from .render import ACCENT, THEME, TurnRenderer, render_diff, set_theme
from .session import Session, list_sessions, state_dir

COMMANDS = {
    "/help": "mostra comandi e scorciatoie",
    "/fast": "modalità veloce (1 agente)",
    "/balanced": "team standard: piano, modifiche, test e review",
    "/deep": "team completo: security, performance, edge case",
    "/ultra-deep": "35 agenti: dibattito sul piano, mega review, ricerca web se serve (lento)",
    "/auto": "modalità scelta dal router (default)",
    "/plan": "modalità piano: l'agente legge e propone, non modifica nulla",
    "/permissions": "modalità dei permessi (ask · auto-edit · plan · auto) e regole salvate",
    "/undo": "annulla le modifiche ai file dell'ultimo turno",
    "/rewind": "torna a un punto precedente (annulla più turni)",
    "/diff": "tutte le modifiche fatte in questa sessione",
    "/chat": "modalità chat: risponde senza toccare i file (usa /apply per salvarli)",
    "/agent": "modalità agente: lavora direttamente sui file (default)",
    "/apply": "scrivi su disco i file dell'ultima risposta (modalità chat)",
    "/init": "crea MYDEVAGENT.md con comandi e convenzioni del progetto",
    "/memory": "mostra la memoria del progetto · /memory <testo> aggiunge una nota",
    "/compact": "riassume la conversazione per liberare contesto",
    "/model": "cambia modello principale · /model <nome>",
    "/models": "modelli installati e modelli in uso",
    "/agents": "elenca gli agenti",
    "/files": "file allegati all'ultimo messaggio",
    "/cost": "token e tempo della sessione",
    "/think": "mostra/nascondi il ragionamento del modello",
    "/index": "indicizza il progetto per la ricerca semantica",
    "/doctor": "verifica backend, modelli, rete, sandbox",
    "/theme": "tema dark / light",
    "/resume": "riprendi una sessione precedente in questa cartella",
    "/export": "salva la conversazione in Markdown",
    "/clear": "nuova conversazione",
    "/exit": "esci",
}
MODES = ("auto", "fast", "balanced", "deep", "ultra-deep")
SHELL_TIMEOUT = 120
MAX_SHELL_OUTPUT = 8000
NOTIFY_AFTER_S = 20
AUTO_COMPACT_MESSAGES = 20


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
        permission_mode: str = "ask",
        agent_mode: bool = True,
        background: bool = True,
    ) -> None:
        self.orch = orchestrator or Orchestrator(load_settings(overrides={"profile": profile} if profile else None))
        self.console = console or Console()
        self.root = (root or Path.cwd()).resolve()
        self.session = session or Session(cwd=str(self.root))
        self.mode = self.session.mode
        self.agent_mode = agent_mode
        self.policy = PermissionPolicy(mode=permission_mode, root=self.root)
        self.checkpoints = CheckpointStore(self.root)
        existing = self.checkpoints.list()
        self.session_start_cp = (existing[-1].id + 1) if existing else 1
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
        self.custom = extras.custom_commands(self.root)
        self._load_prefs()
        all_commands = {**COMMANDS, **{k: v[0] for k, v in self.custom.items()}}
        self.completer = DevCompleter(all_commands, dict(self.orch.registry.by_alias), self.root)
        self.prompt = self._build_prompt(prompt_input, prompt_output)
        if background:
            threading.Thread(target=self._check_online, daemon=True).start()
            extras.warmup(self.orch.llm, self.orch.settings)
            threading.Thread(target=self._auto_index, daemon=True).start()

    # ------------------------------------------------------------ setup
    def _build_prompt(self, prompt_input, prompt_output) -> PromptSession:
        keys = KeyBindings()

        @keys.add("escape", "enter")  # Alt+Enter → nuova riga
        def _newline(event) -> None:
            event.current_buffer.insert_text("\n")

        @keys.add("c-j")  # Ctrl+J → nuova riga (funziona in ogni terminale)
        def _newline2(event) -> None:
            event.current_buffer.insert_text("\n")

        @keys.add("s-tab")  # Shift+Tab → cambia modalità dei permessi, come Claude Code
        def _cycle(event) -> None:
            self.policy.next_mode()
            event.app.invalidate()

        @keys.add("escape", "escape")  # Esc Esc → /rewind
        def _rewind(event) -> None:
            buffer = event.current_buffer
            buffer.text = "/rewind"
            buffer.validate_and_handle()

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
            placeholder=[("class:placeholder", "Chiedi qualcosa… / comandi · @ file · ! shell · # memoria")],
            style=_style(),
            input=prompt_input,
            output=prompt_output,
        )

    def _prefs_path(self) -> Path:
        return state_dir() / "config.json"

    def _load_prefs(self) -> None:
        try:
            prefs = json.loads(self._prefs_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            prefs = {}
        set_theme(prefs.get("theme", "dark"))

    def _save_pref(self, key: str, value: Any) -> None:
        path = self._prefs_path()
        try:
            prefs = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        except ValueError:
            prefs = {}
        prefs[key] = value
        path.write_text(json.dumps(prefs, indent=1), encoding="utf-8")

    def _check_online(self) -> None:
        try:
            self.online = self.orch.toolbox.ctx.connectivity.online()
        except Exception:
            self.online = False

    def _auto_index(self) -> None:
        """Crea l'indice RAG in background alla prima apertura di un progetto (se piccolo abbastanza)."""
        rag = self.orch.settings.tools.rag
        index_file = self.root / rag.index_dir / "index.json"
        if not rag.enabled or index_file.exists() or not (self.root / ".git").exists():
            return
        try:
            count = sum(1 for _ in Workspace(self.root).iter_files())
            if count > 2000:
                return
            from ..tools.rag import CodeIndex

            settings = self.orch.settings.model_copy(deep=True)
            settings.tools.filesystem.root = str(self.root)
            extras_private_dir(self.root)
            CodeIndex.for_workspace(settings, self.orch.llm).build()
        except Exception:
            pass

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
        perm = self.policy.mode
        perm_style = {"ask": "class:tb.dim", "auto-edit": "class:tb.ok", "plan": "class:tb.plan",
                      "auto": "class:tb.warn"}[perm]
        perm_text = {"ask": "⏵ ask", "auto-edit": "⏵⏵ auto-edit", "plan": "⏸ plan", "auto": "⏵⏵⏵ auto"}[perm]
        parts = [
            ("class:tb.key", f" {'agente' if self.agent_mode else 'chat'} "), (perm_style, perm_text),
            ("class:tb.dim", " (shift+tab) · "), ("class:tb", self.model),
            ("class:tb.dim", " · modo "), ("class:tb.key", self.mode), ("class:tb.dim", " · "), net,
            ("class:tb.dim", f" · ~{self.stats['tokens']:,} tok".replace(",", ".")),
        ]
        if self.branch:
            parts.append(("class:tb.dim", f" ·  {self.branch}"))
        return parts

    def banner(self) -> None:
        profile = self.orch.settings.profile
        memory = "MYDEVAGENT.md ✓" if read_memory(self.root) else "nessuna memoria (/init per crearla)"
        body = (
            f"[bold {ACCENT}]✻[/] [bold]Benvenuto in MyDevAgent[/]  [dim]{len(self.orch.registry)} agenti · "
            "local-first[/]\n\n"
            f"[dim]cwd:[/]     {escape(str(self.root))}\n"
            f"[dim]profilo:[/] {profile} · [dim]modello:[/] {self.model}\n"
            f"[dim]memoria:[/] {memory}\n\n"
            "[dim]Suggerimenti:[/]\n"
            "  [dim]•[/] chiedi di modificare il codice: l'agente legge, modifica, lancia i test e ti mostra i diff\n"
            "  [dim]•[/] [bold]/[/] comandi · [bold]@file[/] allega · [bold]![/]shell · [bold]#[/]nota in memoria\n"
            "  [dim]•[/] [bold]Shift+Tab[/] permessi · [bold]Esc[/] interrompe · [bold]/undo[/] annulla · "
            "[bold]Esc Esc[/] torna indietro"
        )
        self.console.print(Panel(body, border_style=ACCENT, expand=False, padding=(0, 2)))
        if self.session.history:
            turns = len(self.session.history) // 2
            self.console.print(f"[dim]⎿  Ripresa sessione «{escape(self.session.title)}» ({turns} turni)[/]")

    # --------------------------------------------------------- domande utente
    def _input(self, message: str) -> str:
        return self.prompt.prompt(message, bottom_toolbar=None, completer=None, placeholder="").strip()

    def ask(self, question: str, allow_always: bool = True) -> str:
        if self._ask:
            return self._ask(question)
        options = "  [dim]1[/] Sì" + ("  [dim]2[/] Sì, e non chiedere più" if allow_always else "") + "  [dim]3[/] No"
        self.console.print(f"[bold]{escape(question)}[/]{options}")
        answer = self._input("  › ")
        valid = ("1", "2", "3") if allow_always else ("1", "3")
        return answer if answer in valid else "3"

    def ask_approval(self, req: ApprovalRequest) -> tuple[str, str]:
        """Conferma di una modifica o di un comando (chiamata dal thread della UI)."""
        c = self.console
        if req.tool in ("edit_file", "write_file"):
            path = req.args.get("path", "")
            c.print(f"\n[{ACCENT}]⏺[/] [bold]{escape(req.summary)}[/]")
            if req.diff:
                c.print(render_diff(req.diff, max_lines=80))
            question = f"Applicare la modifica a {path}?"
        else:  # comando già mostrato dalla riga ⏺ Bash(...)/Test(...) del tool
            if req.dangerous:
                c.print("  [red]⚠ comando potenzialmente distruttivo: controlla bene[/]")
            question = "Eseguire questo comando?"
        choice = self.ask(question, allow_always=not req.dangerous)
        if choice == "1":
            return "yes", ""
        if choice == "2":
            return "always", ""
        feedback = "" if self._ask else self._input("  cosa devo fare invece? (Invio per saltare) › ")
        return "no", feedback

    # ----------------------------------------------------------- comandi
    def handle_command(self, text: str) -> bool:
        """Esegue un comando `/`. Restituisce False per uscire."""
        cmd, _, arg = text.partition(" ")
        cmd, arg = cmd.lower(), arg.strip()
        c = self.console
        if cmd in ("/exit", "/quit"):
            return False
        if cmd == "/help":
            table = Table(show_header=False, box=None, padding=(0, 2))
            for name, desc in {**COMMANDS, **{k: v[0] for k, v in self.custom.items()}}.items():
                table.add_row(f"[bold]{name}[/]", f"[dim]{escape(desc)}[/]")
            c.print(table)
            c.print("[dim]Scorciatoie: Tab completa · ↑/↓ cronologia · Alt+Enter/Ctrl+J nuova riga · Shift+Tab "
                    "permessi · Esc o Ctrl+C interrompe · Esc Esc torna indietro · Ctrl+D esce[/]")
        elif cmd[1:] in MODES and not arg:
            self.mode = self.session.mode = cmd[1:]
            c.print(f"[dim]⎿  modalità: {self.mode}[/]")
        elif cmd in ("/fast", "/balanced", "/deep", "/ultra-deep") and arg:
            self.submit(text)  # "/deep crea un'API" → il router gestisce il comando inline
        elif cmd == "/plan":
            self.policy.mode = "ask" if self.policy.mode == "plan" else "plan"
            c.print(f"[dim]⎿  permessi: {MODE_LABELS[self.policy.mode]}[/]")
            if arg:
                self.submit(arg)
        elif cmd == "/permissions":
            if arg in PERMISSION_MODES:
                self.policy.mode = arg
            c.print(f"[dim]⎿  modalità: [bold]{self.policy.mode}[/] ({MODE_LABELS[self.policy.mode]}) · "
                    f"disponibili: {', '.join(PERMISSION_MODES)}[/]")
            rules = self.policy.allow_rules
            c.print("[dim]   regole «consenti sempre»: " + (", ".join(rules) if rules else "nessuna") + "[/]")
        elif cmd == "/undo":
            undone = self.checkpoints.undo()
            if not undone:
                c.print("[dim]⎿  Niente da annullare.[/]")
            else:
                cp, files = undone
                c.print(f"[green]⏺[/] Annullato «{escape(cp.label)}»\n  [dim]⎿  ripristinati: {', '.join(files)}[/]")
                self.completer.refresh()
        elif cmd == "/rewind":
            self._rewind()
        elif cmd == "/diff":
            diff = self.checkpoints.session_diff(self.session_start_cp)
            if diff.strip():
                c.print(Syntax(diff, "diff", theme=THEME["diff"], word_wrap=True, background_color="default"))
            else:
                c.print("[dim]⎿  Nessuna modifica in questa sessione.[/]")
        elif cmd in ("/chat", "/agent"):
            self.agent_mode = cmd == "/agent"
            c.print(f"[dim]⎿  {'modalità agente: lavoro direttamente sui file' if self.agent_mode else 'modalità chat: rispondo senza modificare i file'}[/]")
        elif cmd == "/apply":
            if not self.last_answer:
                c.print("[dim]⎿  Nessuna risposta da applicare.[/]")
            else:
                written = apply_answer(self.last_answer, self.orch.registry, self.root, c, self.ask)
                if written:
                    self.completer.refresh()
        elif cmd == "/init":
            was_agent, self.agent_mode = self.agent_mode, True
            self.submit(extras.INIT_TASK, display="/init")
            self.agent_mode = was_agent
        elif cmd == "/memory":
            if arg:
                path = append_memory(self.root, arg)
                c.print(f"[dim]⎿  nota aggiunta a {path.name}[/]")
            else:
                memory = read_memory(self.root)
                c.print(Panel(escape(memory) if memory else "[dim]Nessuna memoria. Usa /init o #nota.[/]",
                              title="memoria del progetto", border_style="grey50", expand=False))
        elif cmd == "/compact":
            self._compact(manual=True)
        elif cmd == "/model":
            if not arg:
                c.print(f"[dim]⎿  modello principale: {self.model} · /models per l'elenco[/]")
            else:
                profile = self.orch.settings.active_profile
                profile.main = arg
                if isinstance(profile.reasoning, str) and profile.reasoning == self.model:
                    profile.reasoning = arg
                self.model = arg
                c.print(f"[dim]⎿  modello principale: {escape(arg)} (solo per questa sessione)[/]")
                extras.warmup(self.orch.llm, self.orch.settings)
        elif cmd == "/models":
            self._models()
        elif cmd == "/agents":
            table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
            for col in ("#", "agente", "gruppo", "stage", "alias"):
                table.add_column(col)
            for a in self.orch.registry:
                group = "nucleo" if a.group == "core" else "ultra"
                table.add_row(str(a.id), a.name, group, a.stage, " ".join("@" + x for x in a.aliases))
            c.print(table)
        elif cmd == "/files":
            c.print("[dim]⎿  " + (", ".join(self.last_files) or "nessun file allegato") + "[/]")
        elif cmd == "/cost":
            c.print(f"[dim]⎿  {self.stats['turns']} turni · ~{self.stats['tokens']:,} token · "
                    f"{self.stats['seconds']:.0f}s di lavoro[/]".replace(",", "."))
        elif cmd == "/think":
            self.show_thinking = not self.show_thinking
            c.print(f"[dim]⎿  mostra ragionamento: {'sì' if self.show_thinking else 'no'}[/]")
        elif cmd == "/index":
            self._index()
        elif cmd == "/doctor":
            from ..cli import doctor

            doctor(profile=None)
        elif cmd == "/theme":
            name = arg or ("light" if THEME["diff"] == "ansi_dark" else "dark")
            set_theme(name)
            self._save_pref("theme", name)
            c.print(f"[dim]⎿  tema: {name}[/]")
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
        elif cmd in self.custom:
            self.submit(extras.expand_command(self.custom[cmd][1], arg), display=text)
        else:
            c.print(f"[red]⎿  comando sconosciuto: {escape(cmd)}[/] [dim](/help)[/]")
        return True

    def _rewind(self) -> None:
        checkpoints = self.checkpoints.list()
        if not checkpoints:
            self.console.print("[dim]⎿  Nessun punto a cui tornare.[/]")
            return
        recent = checkpoints[-10:]
        for i, cp in enumerate(reversed(recent), start=1):
            when = time.strftime("%H:%M", time.localtime(cp.created))
            self.console.print(f"  [bold]{i}[/] [dim]{when}[/] {escape(cp.label[:60])} [dim]({len(cp.files)} file)[/]")
        choice = self._input("  torna a prima di (numero) › ") if not self._ask else self._ask("rewind")
        if choice.isdigit() and 1 <= int(choice) <= len(recent):
            target = list(reversed(recent))[int(choice) - 1]
            files = self.checkpoints.rewind(target.id)
            self.console.print(f"[green]⏺[/] Tornato a prima di «{escape(target.label[:60])}»\n"
                               f"  [dim]⎿  ripristinati: {', '.join(files)}[/]")
            self.completer.refresh()

    def _models(self) -> None:
        installed, url = extras.list_models(self.orch.settings)
        if installed is None:
            self.console.print(f"[red]⎿  backend non raggiungibile: {url}[/] [dim](avvia Ollama: `ollama serve`)[/]")
            return
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("tier")
        table.add_column("modello")
        table.add_column("")
        for tier in ("main", "fast", "reasoning", "embed", "vision"):
            model, _ = self.orch.settings.resolve_model(tier)
            ok = model in installed or f"{model}:latest" in installed
            table.add_row(tier, model, "[green]✓[/]" if ok else f"[red]✗ ollama pull {model}[/]")
        self.console.print(table)
        self.console.print("[dim]Installati: " + ", ".join(sorted(installed)) + "[/]")

    def _index(self) -> None:
        from ..tools.rag import CodeIndex

        settings = self.orch.settings.model_copy(deep=True)
        settings.tools.filesystem.root = str(self.root)
        index = CodeIndex.for_workspace(settings, self.orch.llm)
        extras_private_dir(self.root)
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
        choice = self._input("  numero › ")
        if choice.isdigit() and 1 <= int(choice) <= len(sessions):
            self.session = sessions[int(choice) - 1]
            self.mode = self.session.mode
            self.last_answer = next((m["content"] for m in reversed(self.session.history)
                                     if m["role"] == "assistant"), "")
            self.console.print(f"[dim]⎿  Ripresa «{escape(self.session.title)}»[/]")

    def _compact(self, manual: bool = False) -> None:
        if len(self.session.history) < 4:
            if manual:
                self.console.print("[dim]⎿  Conversazione ancora corta, niente da compattare.[/]")
            return
        with self.console.status(f"[{ACCENT}]✻ Compatto la conversazione…[/]"):
            try:
                compacted = extras.compact_history(self.orch.llm, self.session.history)
            except Exception as exc:
                self.console.print(f"[red]⎿  compattazione fallita: {escape(str(exc))}[/]")
                return
        before = len(self.session.history) // 2
        self.session.history = compacted
        self.session.save()
        self.console.print(f"[dim]⎿  {before} turni riassunti in un messaggio (/compact)[/]")

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

    def submit(self, text: str, display: str | None = None) -> str:
        if len(self.session.history) >= AUTO_COMPACT_MESSAGES:
            self._compact()
        files = self.collect_attachments(text)
        for name in files:
            self.console.print(f"  [dim]⎿  allegato {escape(name)}[/]")
        files.update(self.pending_context)
        self.pending_context = {}
        self.last_files = files
        answer = self.run_turn(text, files)
        self.session.add_turn(display or text, answer)
        return answer

    def run_turn(self, text: str, files: dict[str, str]) -> str:
        events: queue.Queue = queue.Queue()
        cancel = threading.Event()
        renderer = TurnRenderer(self.console, self.names)
        started = time.monotonic()
        pending_replies: list[queue.Queue] = []
        mode = None if self.mode == "auto" else self.mode

        def approver(req: ApprovalRequest) -> tuple[str, str]:
            reply: queue.Queue = queue.Queue(maxsize=1)
            pending_replies.append(reply)
            events.put(("approval", (req, reply)))
            return reply.get()

        def worker() -> None:
            try:
                if self.agent_mode:
                    extras_private_dir(self.root)
                    runner = AgentRunner(self.orch, self.root, self.policy, approver=approver,
                                         checkpoints=self.checkpoints)
                    stream = runner.run(text, history=self.session.history, files=files, mode=mode,
                                        on_event=lambda e: events.put(("event", e)), cancel=cancel)
                else:
                    stream = self.orch.run(text, history=self.session.history, files=files, mode=mode,
                                           on_event=lambda e: events.put(("event", e)),
                                           show_thinking=self.show_thinking, cancel=cancel)
                for chunk in stream:
                    events.put(("chunk", chunk))
            except Exception as exc:
                events.put(("error", f"{type(exc).__name__}: {exc}"))
            finally:
                events.put(("done", None))

        threading.Thread(target=worker, daemon=True).start()
        abandoned = False
        watcher = EscWatcher()

        def interrupt() -> bool:
            """Primo Esc/Ctrl+C: ferma il team. Secondo: abbandona. Restituisce True per uscire dal ciclo."""
            if cancel.is_set():
                return True
            cancel.set()
            renderer.cancelled = True
            renderer.status = "Interrompo (di nuovo per forzare)"
            for reply in pending_replies:
                if reply.empty():
                    reply.put(("no", "interrupted by the user"))
            return False

        with watcher, Live(renderer.view(), console=self.console, refresh_per_second=12, transient=True) as live:
            while True:
                try:
                    if watcher.pressed() and interrupt():
                        abandoned = True
                        break
                    try:
                        kind, value = events.get(timeout=0.08)
                    except queue.Empty:
                        live.update(renderer.view())
                        continue
                    if kind == "done":
                        break
                    if kind == "approval":
                        req, reply = value
                        if cancel.is_set():
                            reply.put(("no", "interrupted by the user"))
                            continue
                        live.stop()
                        watcher.__exit__(None, None, None)
                        try:
                            answer = self.ask_approval(req)
                        except (KeyboardInterrupt, EOFError):
                            answer = ("no", "")
                            interrupt()
                        if answer[0] != "no" and req.tool in ("edit_file", "write_file"):
                            renderer.shown_diffs.add(req.args.get("path", ""))
                        reply.put(answer)
                        watcher.__enter__()
                        live.start()
                    elif kind == "error":
                        self.console.print(f"[red]⏺ Errore: {escape(value)}[/]\n  [dim]⎿  prova /models o "
                                           "/doctor[/]")
                    elif kind == "chunk":
                        renderer.on_chunk(value)
                    else:
                        renderer.on_event(value)
                    live.update(renderer.view())
                except KeyboardInterrupt:
                    if interrupt():
                        abandoned = True
                        break
            live.update("")
        renderer.finish()
        if abandoned:
            self.console.print("[dim]  ⎿  l'agente in corso terminerà in background[/]")
        elapsed = time.monotonic() - started
        self.stats["turns"] += 1
        self.stats["seconds"] += elapsed
        self.stats["tokens"] += renderer.tokens + len(renderer.answer) // 4
        if elapsed > NOTIFY_AFTER_S and not self._ask:
            extras.notify("MyDevAgent", "Ho finito" if not renderer.cancelled else "Interrotto")
        answer = renderer.answer + ("\n\n[interrotto]" if renderer.cancelled else "")
        self.last_answer = renderer.answer
        self.completer.refresh()
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
            if text.startswith("#") and not text.startswith("##") and len(text) > 1:
                path = append_memory(self.root, text[1:])
                self.console.print(f"[dim]⎿  nota salvata in {path.name}[/]")
                continue
            if text.startswith("/") and not text.startswith("//"):
                if not self.handle_command(text):
                    break
                continue
            self.submit(text)
        self.session.save()
        self.console.print(f"[dim]Sessione salvata: {self.session.id} · riprendi con `mydevagent --continue`[/]")


def extras_private_dir(root: Path) -> None:
    """`.mydevagent/` nel progetto con un .gitignore interno: checkpoint e cache non finiscono in git."""
    folder = root / ".mydevagent"
    try:
        folder.mkdir(exist_ok=True)
        ignore = folder / ".gitignore"
        if not ignore.exists():
            ignore.write_text("*\n", encoding="utf-8")
    except OSError:
        pass


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
        "tb.plan": "#6fa8dc",
        "completion-menu.completion": "bg:#2b2b2b #d0d0d0",
        "completion-menu.completion.current": f"bg:{ACCENT} #ffffff",
        "completion-menu.meta.completion": "bg:#2b2b2b #8a8a8a",
        "completion-menu.meta.completion.current": f"bg:{ACCENT} #ffffff",
    })


def run_tui(profile: str | None = None, continue_last: bool = False, permission_mode: str = "ask") -> None:
    session = None
    if continue_last:
        previous = list_sessions(str(Path.cwd().resolve()), limit=1)
        session = previous[0] if previous else None
    TuiApp(profile=profile, session=session, permission_mode=permission_mode).loop()
