"""Funzioni di supporto della UI: comandi personalizzati, compattazione, notifiche, warmup, modelli."""

from __future__ import annotations

import contextlib
import os
import platform
import shutil
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import httpx

COMPACT_PROMPT = (
    "Summarize this conversation between a user and a coding agent so work can continue. Keep: the user's "
    "goals and preferences, decisions taken, files changed and why, commands/tests and their results, open "
    "problems and next steps. Be dense, bullet points, max 300 words. Reply in the conversation's language."
)
INIT_TASK = (
    "Analyze this project with the tools (list_files, read_file on README/config/manifests, grep) and create "
    "the file MYDEVAGENT.md in the project root with these sections, max ~60 lines, only verified facts:\n"
    "# <project name>\n## Overview (2-3 lines)\n## Commands (build, run, test, lint — exact commands, "
    "format `- test: <command>`)\n## Architecture (main folders/modules and their role)\n"
    "## Conventions (style, naming, patterns, libraries to prefer)\n## Notes (pitfalls, things to avoid)\n"
    "If MYDEVAGENT.md already exists, improve it instead of overwriting useful content."
)


# ------------------------------------------------------------ comandi custom
def custom_commands(root: Path) -> dict[str, tuple[str, str]]:
    """`.mydevagent/commands/<nome>.md` (progetto) e `~/.mydevagent/commands` (utente) → /nome.

    Nel file `$ARGUMENTS` viene sostituito con il testo dopo il comando. La prima riga che inizia
    con `description:` diventa la descrizione mostrata nel completamento.
    """
    state = Path(os.environ.get("MYDEVAGENT_STATE_DIR", Path.home() / ".mydevagent"))
    out: dict[str, tuple[str, str]] = {}
    for folder in (state / "commands", root / ".mydevagent" / "commands"):
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            desc = "comando personalizzato"
            lines = text.splitlines()
            if lines and lines[0].lower().startswith("description:"):
                desc = lines[0].split(":", 1)[1].strip()
                text = "\n".join(lines[1:]).strip()
            out["/" + path.stem.lower()] = (desc, text)
    return out


def expand_command(template: str, arguments: str) -> str:
    if "$ARGUMENTS" in template:
        return template.replace("$ARGUMENTS", arguments)
    return f"{template}\n\n{arguments}".strip()


# ------------------------------------------------------------- compattazione
def history_chars(history: list[dict[str, Any]]) -> int:
    return sum(len(str(m.get("content", ""))) for m in history)


def compact_history(llm, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    transcript = "\n\n".join(f"{m['role']}: {m['content']}" for m in history)[-60_000:]
    summary = llm.complete([{"role": "system", "content": COMPACT_PROMPT},
                            {"role": "user", "content": transcript}], tier="fast", max_tokens=600,
                           temperature=0.1).text.strip()
    return [{"role": "user", "content": "[Summary of the previous conversation]\n" + summary},
            {"role": "assistant", "content": "OK, I have the context. Let's continue."}]


# ------------------------------------------------------------------ notifiche
def notify(title: str, message: str) -> None:
    """Campanella del terminale + notifica desktop se disponibile (mai bloccante)."""
    sys.stdout.write("\a")
    sys.stdout.flush()
    try:
        system = platform.system()
        if system == "Linux" and shutil.which("notify-send"):
            subprocess.Popen(["notify-send", title, message], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif system == "Darwin":
            clean = message.replace('"', "'")
            script = f'display notification "{clean}" with title "{title}"'
            subprocess.Popen(["osascript", "-e", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


# --------------------------------------------------------- modelli e warmup
def list_models(settings) -> tuple[set[str] | None, str]:
    model, backend = settings.resolve_model("main")
    try:
        resp = httpx.get(backend.base_url.rstrip("/") + "/models",
                         headers={"Authorization": f"Bearer {backend.api_key}"}, timeout=3)
        resp.raise_for_status()
        return {m["id"] for m in resp.json().get("data", [])}, backend.base_url
    except Exception:
        return None, backend.base_url


def warmup(llm, settings) -> threading.Thread:
    """Carica il modello principale in memoria in background: la prima risposta non paga il caricamento."""

    def run() -> None:
        with contextlib.suppress(Exception):
            llm.complete([{"role": "user", "content": "ok"}], tier="main", max_tokens=1, temperature=0.0)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread
