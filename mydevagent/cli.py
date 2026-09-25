"""CLI: mydevagent (UI interattiva) | chat | ask | serve | index | doctor | agents | route."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

app = typer.Typer(add_completion=False,
                  help="MyDevAgent — assistente di programmazione local-first con 15 agenti. "
                       "Senza comandi apre l'interfaccia interattiva.")
console = Console()
err = Console(stderr=True)


def _orchestrator(profile: str | None = None):
    from .config import load_settings
    from .orchestrator import Orchestrator

    overrides = {"profile": profile} if profile else None
    return Orchestrator(load_settings(overrides=overrides))


def _event_printer(target: Console, quiet: bool = False):
    def on_event(event: dict[str, Any]) -> None:
        if quiet:
            return
        kind = event["type"]
        if kind == "route":
            target.print(f"[dim]⟢ {event['mode']} · {' → '.join(event['agents'])}[/dim]")
        elif kind == "agent_start" and event["agent"] not in ("final",):
            target.print(f"[dim]  ▸ {event['name']}…[/dim]")
        elif kind == "agent_end" and event["agent"] != "final":
            tokens = event.get("prompt_tokens", 0) + event.get("completion_tokens", 0)
            mark = "[red]✗[/red]" if event.get("error") else "[green]✓[/green]"
            extra = f" [red]{event['error']}[/red]" if event.get("error") else ""
            target.print(f"[dim]  {mark} {event['name']} {event['ms'] / 1000:.1f}s · {tokens} tok{extra}[/dim]")
        elif kind == "info":
            target.print(f"[dim]  · {event['text']}[/dim]")
        elif kind == "done":
            target.print(f"\n[dim]{event['summary']}[/dim]")

    return on_event


def _read_files(paths: list[Path] | None) -> dict[str, str]:
    files = {}
    for path in paths or []:
        files[str(path)] = path.read_text(encoding="utf-8", errors="replace")
    return files


def _images(paths: list[Path] | None) -> list[str]:
    from .tools.vision import image_to_data_url

    return [image_to_data_url(p) for p in paths or []]


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    profile: str = typer.Option(None, "--profile", "-p", help="cpu | gpu8 | gpu16 | gpu24"),
    continue_last: bool = typer.Option(False, "--continue", "-c", help="Riprendi l'ultima sessione in questa cartella"),
    permissions: str = typer.Option("ask", "--permissions", help="ask | auto-edit | plan | auto"),
) -> None:
    """Senza sottocomando apre l'interfaccia interattiva stile Claude Code."""
    if ctx.invoked_subcommand is None:
        from .tui import run_tui

        run_tui(profile, continue_last=continue_last, permission_mode=permissions)


@app.command()
def ask(
    request: str = typer.Argument(..., help="La richiesta ('-' per leggere da stdin)"),
    file: list[Path] = typer.Option(None, "--file", "-f", exists=True, help="File da allegare (ripetibile)"),
    image: list[Path] = typer.Option(None, "--image", "-i", exists=True, help="Screenshot/mockup (ripetibile)"),
    mode: str = typer.Option("auto", "--mode", "-m", help="auto | fast | balanced | deep"),
    profile: str = typer.Option(None, "--profile", "-p", help="cpu | gpu8 | gpu16 | gpu24"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Solo la risposta, senza avanzamento agenti"),
    think: bool = typer.Option(False, "--show-thinking", help="Mostra i blocchi <think> del modello"),
) -> None:
    """Una singola richiesta, risposta in streaming su stdout."""
    if request == "-":
        request = sys.stdin.read()
    orch = _orchestrator(profile)
    on_event = _event_printer(err, quiet)
    try:
        for chunk in orch.run(request, files=_read_files(file), images=_images(image), mode=mode,
                              on_event=on_event, show_thinking=think):
            sys.stdout.write(chunk)
            sys.stdout.flush()
    except Exception as exc:
        _print_error(err, exc, orch.settings)
        raise typer.Exit(1) from None
    sys.stdout.write("\n")


def _print_error(target: Console, exc: Exception, settings) -> None:
    from .health import explain_error

    title, hint = explain_error(exc, settings)
    target.print(f"\n[red]✗ {escape(title)}[/red]\n[dim]→ {escape(hint)}[/dim]")


CHAT_HELP = """[bold]Comandi[/bold]: /fast /balanced /deep /auto (modalità) · /file <path> (allega) · /image <path>
/files (elenco allegati) · /clear-files · /think (mostra ragionamento) · /reset (nuova conversazione)
/agents · /exit   —   nel testo: @security @perf @web @db ... per coinvolgere agenti specifici"""


@app.command()
def chat(
    profile: str = typer.Option(None, "--profile", "-p", help="cpu | gpu8 | gpu16 | gpu24"),
    mode: str = typer.Option("auto", "--mode", "-m"),
    plain: bool = typer.Option(False, "--plain", help="Chat semplice (terminali limitati, pipe)"),
    continue_last: bool = typer.Option(False, "--continue", "-c"),
) -> None:
    """Chat interattiva (stessa UI di `mydevagent`; --plain per la versione semplice)."""
    if not plain and sys.stdin.isatty():
        from .tui import run_tui

        run_tui(profile, continue_last=continue_last)
        return
    orch = _orchestrator(profile)
    history: list[dict[str, Any]] = []
    files: dict[str, str] = {}
    images: list[str] = []
    show_thinking = False
    model, _ = orch.settings.resolve_model("main")
    console.print(f"[bold cyan]MyDevAgent[/bold cyan] · profilo [bold]{orch.settings.profile}[/bold] · "
                  f"modello {model} · 15 agenti")
    console.print(CHAT_HELP)
    while True:
        try:
            text = console.input("\n[bold green]› [/bold green]").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text:
            continue
        cmd, _, arg = text.partition(" ")
        if cmd in ("/exit", "/quit"):
            break
        if cmd in ("/fast", "/balanced", "/deep", "/auto") and not arg:
            mode = cmd[1:]
            console.print(f"[dim]modalità: {mode}[/dim]")
            continue
        if cmd == "/reset":
            history, files, images = [], {}, []
            console.print("[dim]conversazione azzerata[/dim]")
            continue
        if cmd == "/think":
            show_thinking = not show_thinking
            console.print(f"[dim]mostra ragionamento: {show_thinking}[/dim]")
            continue
        if cmd == "/agents":
            agents()
            continue
        if cmd == "/files":
            console.print("[dim]" + (", ".join(files) or "nessun file allegato") + "[/dim]")
            continue
        if cmd == "/clear-files":
            files, images = {}, []
            continue
        if cmd in ("/file", "/image"):
            path = Path(arg).expanduser()
            if not path.is_file():
                console.print(f"[red]file non trovato: {path}[/red]")
                continue
            if cmd == "/file":
                files.update(_read_files([path]))
            else:
                images.extend(_images([path]))
            console.print(f"[dim]allegato: {path}[/dim]")
            continue

        answer = []
        try:
            for chunk in orch.run(text, history=history, files=files, images=images, mode=mode,
                                  on_event=_event_printer(console), show_thinking=show_thinking):
                answer.append(chunk)
                console.print(chunk, end="", markup=False, highlight=False, soft_wrap=True)
        except KeyboardInterrupt:
            console.print("\n[yellow]interrotto[/yellow]")
        except Exception as exc:
            _print_error(console, exc, orch.settings)
            continue
        images = []  # le immagini valgono per un solo turno
        history += [{"role": "user", "content": text}, {"role": "assistant", "content": "".join(answer)}]


@app.command()
def serve(
    host: str = typer.Option(None, help="Default da settings.yaml (127.0.0.1)"),
    port: int = typer.Option(None, help="Default da settings.yaml (8000)"),
) -> None:
    """Avvia il server compatibile OpenAI (per VS Code/Continue, Cursor, Aider, Cline...)."""
    from .server import serve as run_server

    run_server(host, port)


@app.command()
def index(
    path: Path = typer.Argument(Path("."), help="Root del progetto da indicizzare"),
    no_embeddings: bool = typer.Option(False, help="Solo indice lessicale (niente modello di embedding)"),
) -> None:
    """Indicizza la codebase per il RAG locale (salvato in <path>/.mydevagent/index.json)."""
    from .config import load_settings
    from .llm import build_llm
    from .tools.rag import CodeIndex

    settings = load_settings(overrides={"tools": {"filesystem": {"root": str(path.resolve())}}})
    idx = CodeIndex.for_workspace(settings, build_llm(settings))
    with console.status("indicizzazione…"):
        stats = idx.build(use_embeddings=not no_embeddings)
    kind = "semantico" if stats["embedded"] else "lessicale (embeddings non disponibili)"
    console.print(f"[green]✓[/green] {stats['chunks']} chunk indicizzati · indice {kind} · {idx.path}")


@app.command()
def agents() -> None:
    """Elenca gli agenti (15 nucleo + 20 ultra-deep)."""
    from .config import get_settings
    from .registry import load_registry

    registry = load_registry(get_settings())
    table = Table(title=f"MyDevAgent — {len(registry)} agenti (15 nucleo + {len(registry.ultra())} ultra-deep)",
                  show_lines=False)
    for col in ("#", "Agente", "Gruppo", "Stage", "Tier", "Alias"):
        table.add_column(col)
    for a in registry:
        table.add_row(str(a.id), a.name, "nucleo" if a.group == "core" else "ultra", a.stage, a.tier,
                      " ".join("@" + x for x in a.aliases))
    console.print(table)


@app.command()
def route(request: str, as_json: bool = typer.Option(False, "--json")) -> None:
    """Mostra quale modalità e quali agenti verrebbero usati (nessuna chiamata LLM)."""
    from .config import get_settings
    from .registry import load_registry
    from .router import Router

    settings = get_settings()
    r = Router(settings, load_registry(settings)).route(request)
    data = {"mode": r.mode, "agents": r.agents, "primary": r.primary, "specialists": r.specialists,
            "gate": r.gate, "research": r.research, "reasons": r.reasons, "scores": r.scores}
    if as_json:
        console.print_json(json.dumps(data))
    else:
        console.print(f"[bold]{r.mode}[/bold] → {' → '.join(r.agents)}\n[dim]{'; '.join(r.reasons)}[/dim]")


@app.command()
def bench(
    profile: str = typer.Option(None, "--profile", "-p"),
    tiers: str = typer.Option("main,fast", help="tier da misurare, separati da virgola"),
) -> None:
    """Misura primo token e velocità (token/s) dei modelli sul tuo hardware e consiglia il profilo."""
    import time

    from .config import load_settings
    from .llm import build_llm

    settings = load_settings(overrides={"profile": profile} if profile else None)
    llm = build_llm(settings)
    prompt = [{"role": "system", "content": "You are a concise senior engineer."},
              {"role": "user", "content": "Write a Python function that returns the n-th Fibonacci number "
                                          "iteratively, with type hints and a docstring. Code only."}]
    table = Table(title=f"Benchmark · profilo {settings.profile}")
    for col in ("tier", "modello", "primo token", "token/s", "totale"):
        table.add_column(col)
    speeds: dict[str, float] = {}
    for tier in [t.strip() for t in tiers.split(",") if t.strip()]:
        model = settings.resolve_model(tier)[0]
        try:
            llm.complete([{"role": "user", "content": "ok"}], tier=tier, max_tokens=1)  # warmup/caricamento
            start = time.perf_counter()
            first = None
            text = ""
            for chunk in llm.stream(prompt, tier=tier, max_tokens=256, temperature=0.0):
                if first is None:
                    first = time.perf_counter() - start
                text += chunk
            total = time.perf_counter() - start
            tokens = max(1, len(text) // 4)
            gen_time = max(1e-3, total - (first or 0))
            speeds[tier] = tokens / gen_time
            table.add_row(tier, model, f"{(first or 0):.2f}s", f"{speeds[tier]:.1f}", f"{total:.1f}s")
        except Exception as exc:
            table.add_row(tier, model, "[red]errore[/red]", "-", f"[red]{type(exc).__name__}[/red]")
    console.print(table)
    main_speed = speeds.get("main")
    if main_speed is None:
        console.print("[yellow]Nessuna misura sul modello principale: controlla `mydevagent doctor`.[/yellow]")
        return
    order = ["cpu", "gpu8", "gpu16", "gpu24"]
    idx = order.index(settings.profile) if settings.profile in order else 1
    if main_speed < 8 and idx > 0:
        console.print(f"[yellow]Lento ({main_speed:.0f} tok/s): prova il profilo [bold]{order[idx - 1]}[/bold] "
                      "o /fast per le richieste semplici.[/yellow]")
    elif main_speed > 45 and idx < len(order) - 1:
        console.print(f"[green]Veloce ({main_speed:.0f} tok/s): puoi provare il profilo [bold]{order[idx + 1]}"
                      "[/bold] per più qualità.[/green]")
    else:
        console.print(f"[green]Il profilo {settings.profile} è adatto a questo PC ({main_speed:.0f} tok/s).[/green]")
    console.print("[dim]Stima token ≈ caratteri/4. Consigli di velocità: docs/PERFORMANCE.md[/dim]")


@app.command()
def doctor(profile: str = typer.Option(None, "--profile", "-p")) -> None:
    """Verifica backend LLM, modelli, connessione, ricerca web, sandbox e indice RAG."""
    import os

    from .config import load_settings
    from .health import (
        OPTIONAL_TIERS,
        check_backends,
        detect_hardware,
        is_ollama,
        recommend_profile,
        start_hint,
    )
    from .tools.connectivity import Connectivity
    from .tools.sandbox import Sandbox
    from .tools.web_search import PROVIDERS

    settings = load_settings(overrides={"profile": profile} if profile else None)
    ok = "[green]✓[/green]"
    ko = "[red]✗[/red]"
    warn = "[yellow]![/yellow]"
    console.print(f"[bold]Profilo[/bold]: {settings.profile}")

    health = check_backends(settings, timeout=3)
    for url, reachable in health.reachable.items():
        if reachable:
            console.print(f"{ok} backend raggiungibile: {url}")
        else:
            console.print(f"{ko} backend non raggiungibile: {url} — {start_hint(url)}")
    for status in health.tiers:
        if status.installed is None:
            continue
        optional = " [dim](opzionale)[/dim]" if status.tier in OPTIONAL_TIERS else ""
        console.print(f"  {ok if status.installed else warn} {status.tier:<9} {status.model}{optional}")
    missing = [s.model for s in health.missing()]
    if missing and is_ollama(settings.backends[settings.default_backend].base_url):
        console.print("  [dim]scarica i modelli mancanti:[/dim] " + " && ".join(f"ollama pull {m}"
                                                                           for m in dict.fromkeys(missing)))
    hw = detect_hardware()
    best = recommend_profile(hw)
    same = best == settings.profile
    console.print(f"{ok if same else warn} hardware: {hw.describe()} → profilo consigliato [bold]{best}[/bold]"
                  + ("" if same else f" (ora usi {settings.profile}: `mydevagent -p {best}`)"))

    online = Connectivity(settings.tools.connectivity).online()
    console.print(f"{ok if online else warn} internet: {'online' if online else 'offline (ricerca web disattivata)'}")
    configured = [name for name in settings.tools.web.providers
                  if name in PROVIDERS and PROVIDERS[name](5).available()]
    console.print(f"{ok if configured else warn} ricerca web: {', '.join(configured) or 'nessun provider'}"
                  + ("" if configured else " — imposta TAVILY_API_KEY o `pip install ddgs`"))
    backend = Sandbox(settings.tools.sandbox).backend()
    if backend == "docker":
        console.print(f"{ok} sandbox: docker")
    else:
        hint = "installa Docker" if not shutil.which("docker") else "abilita tools.sandbox"
        console.print(f"{warn} sandbox: {backend or 'non disponibile'} — {hint}")
    root = Path(settings.tools.filesystem.root).resolve()
    rag_index = root / settings.tools.rag.index_dir / "index.json"
    console.print(f"{ok if rag_index.is_file() else warn} indice RAG: "
                  f"{rag_index if rag_index.is_file() else 'assente — esegui `mydevagent index`'}")
    if os.environ.get("MYDEVAGENT_API_KEY"):
        console.print(f"{ok} server: protetto da MYDEVAGENT_API_KEY")


if __name__ == "__main__":
    app()
