"""Progetti pronti per /new: ogni cartella qui accanto è un modello, copiato così com'è.

I file con il punto davanti (.gitignore, .env.example) qui si chiamano senza punto, così finiscono anche
nel pacchetto pip: /new li rinomina."""

from __future__ import annotations

import contextlib
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = {
    "sito": "sito web con HTML, CSS e JavaScript (non serve installare niente)",
    "gioco": "gioco 2D con Pygame: acchiappa le stelle",
    "bot-discord": "bot Discord con i comandi !ciao e !dado",
    "api": "API web con FastAPI, con i test",
    "python": "programma Python con i test, per iniziare",
}
DOTFILES = {"gitignore": ".gitignore", "env.example": ".env.example"}


def _is_empty(folder: Path) -> bool:
    return not any(not p.name.startswith(".") for p in folder.iterdir())


def target_for(root: Path, template: str, name: str = "") -> Path:
    """Dove creare il progetto: nella cartella aperta se è vuota, altrimenti in una sottocartella nuova.
    Mai dentro la cartella di MyDevAgent: lì il progetto va accanto."""
    from ..update import HOME

    if name and not re.fullmatch(r"[\w][\w.-]*", name):
        raise ValueError(f"nome non valido: {name} (usa lettere, numeri, - e _)")
    root = root.resolve()
    if root == HOME:
        root = root.parent
    elif not name and _is_empty(root):
        return root
    if name:
        dest = root / name
        if dest.exists() and not _is_empty(dest):
            raise ValueError(f"la cartella {dest} esiste già e non è vuota: scegli un altro nome")
        return dest
    dest, n = root / template, 2
    while dest.exists() and not _is_empty(dest):
        dest, n = root / f"{template}-{n}", n + 1
    return dest


def create(template: str, dest: Path) -> list[str]:
    """Copia il modello in `dest` (e fa `git init` se git c'è). Restituisce i file creati."""
    source = HERE / template
    if template not in TEMPLATES or not source.is_dir():
        raise ValueError(f"modello sconosciuto: {template}")
    dest.mkdir(parents=True, exist_ok=True)
    created = []
    for path in sorted(source.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(source)
        rel = rel.with_name(DOTFILES.get(rel.name, rel.name))
        (dest / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest / rel)
        created.append(rel.as_posix())
    if not (dest / ".git").exists():
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):  # senza git funziona lo stesso
            subprocess.run(["git", "init", "-q"], cwd=dest, capture_output=True, timeout=20)
    return created
