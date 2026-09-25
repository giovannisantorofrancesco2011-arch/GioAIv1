"""CLI: mydevagent chat | ask | serve | index | doctor | agents | route."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="MyDevAgent — assistente di programmazione local-first con 15 agenti.")
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
    for chunk in orch.run(request, files=_read_files(file), images=_images(image), mode=mode,
                          on_event=on_event, show_thinking=think):
        sys.stdout.write(chunk)
        sys.stdout.flush()
    sys.stdout.write("\n")


CHAT_HELP = """[bold]Comandi[/bold]: /fast /balanced /deep /auto (modalità) · /file <path> (allega) · /image <path>
/files (elenco allegati) · /clear-files · /think (mostra ragionamento) · /reset (nuova conversazione)
/agents · /exit   —   nel testo: @security @perf @web @db ... per coinvolgere agenti specifici"""


@app.command()
def chat(
    profile: str = typer.Option(None, "--profile", "-p", help="cpu | gpu8 | gpu16 | gpu24"),
    mode: str = typer.Option("auto", "--mode", "-m"),
) -> None:
    """Chat interattiva nel terminale."""
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
            console.print(f"\n[red]Errore: {type(exc).__name__}: {exc}[/red]\n[dim]Prova `mydevagent doctor`.[/dim]")
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
    """Elenca i 15 agenti."""
    from .config import get_settings
    from .registry import load_registry

    registry = load_registry(get_settings())
    table = Table(title="MyDevAgent — 15 agenti", show_lines=False)
    for col in ("#", "Agente", "Stage", "Tier", "Tool", "Alias"):
        table.add_column(col)
    for a in registry:
        table.add_row(str(a.id), a.name, a.stage, a.tier, ", ".join(a.tools) or "—",
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
def doctor(profile: str = typer.Option(None, "--profile", "-p")) -> None:
    """Verifica backend LLM, modelli, connessione, ricerca web, sandbox e indice RAG."""
    import os

    import httpx

    from .config import TIERS, load_settings
    from .tools.connectivity import Connectivity
    from .tools.sandbox import Sandbox
    from .tools.web_search import PROVIDERS

    settings = load_settings(overrides={"profile": profile} if profile else None)
    ok = "[green]✓[/green]"
    ko = "[red]✗[/red]"
    warn = "[yellow]![/yellow]"
    console.print(f"[bold]Profilo[/bold]: {settings.profile}")

    backends: dict[str, set[str] | None] = {}
    missing: list[str] = []
    for tier in TIERS:
        model, backend = settings.resolve_model(tier)
        if backend.base_url not in backends:
            try:
                resp = httpx.get(backend.base_url.rstrip("/") + "/models",
                                 headers={"Authorization": f"Bearer {backend.api_key}"}, timeout=3)
                resp.raise_for_status()
                backends[backend.base_url] = {m["id"] for m in resp.json().get("data", [])}
                console.print(f"{ok} backend raggiungibile: {backend.base_url}")
            except Exception as exc:
                backends[backend.base_url] = None
                console.print(f"{ko} backend non raggiungibile: {backend.base_url} ({type(exc).__name__})")
        available = backends[backend.base_url]
        if available is None:
            continue
        present = model in available or f"{model}:latest" in available
        console.print(f"  {ok if present else warn} {tier:<9} {model}")
        if not present:
            missing.append(model)
    if missing and "11434" in settings.backends[settings.default_backend].base_url:
        console.print("  [dim]scarica i modelli mancanti:[/dim] " + " && ".join(f"ollama pull {m}"
                                                                           for m in dict.fromkeys(missing)))

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
