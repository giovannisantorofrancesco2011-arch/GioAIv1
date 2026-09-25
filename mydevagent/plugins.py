"""Plugin nel formato di Claude Code: una cartella con `.claude-plugin/plugin.json` e dentro `commands/`
(comandi `/nome`), `skills/` (skill) e `agents/` (agenti specializzati, per MyDevAgent sono skill).
`hooks/` e `.mcp.json` vengono riconosciuti ma non ancora usati.

Da dove arrivano: `.mydevagent/plugins/` del progetto, `~/.mydevagent/plugins/` (dove li mette
`/plugin install`), i plugin installati in Claude Code (`~/.claude/plugins/installed_plugins.json`) e le
cartelle in MYDEVAGENT_PLUGINS_DIRS. Un repository marketplace (`.claude-plugin/marketplace.json`) può
contenere più plugin.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

KINDS = ("commands", "skills", "agents")
PATTERNS = {"commands": "**/*.md", "skills": "*/SKILL.md", "agents": "*.md"}


@dataclass
class Plugin:
    name: str
    path: Path
    source: str  # progetto · utente · claude code · extra
    manifest: dict = field(default_factory=dict)

    @property
    def description(self) -> str:
        return str(self.manifest.get("description") or "")

    @property
    def version(self) -> str:
        return str(self.manifest.get("version") or "")

    def dirs(self, kind: str) -> list[Path]:
        """La cartella standard più quelle indicate nel plugin.json (che si aggiungono, come in Claude Code)."""
        extra = self.manifest.get(kind) or []
        extra = [extra] if isinstance(extra, str) else extra
        paths = [self.path / kind] + [(self.path / e).resolve() for e in extra if isinstance(e, str)]
        return [p for p in dict.fromkeys(paths) if p.is_dir()]

    def count(self, kind: str) -> int:
        return sum(1 for d in self.dirs(kind) for _ in d.glob(PATTERNS[kind]))

    def unsupported(self) -> list[str]:
        out = []
        if (self.path / "hooks").is_dir() or self.manifest.get("hooks"):
            out.append("hook")
        if (self.path / ".mcp.json").is_file() or self.manifest.get("mcpServers"):
            out.append("MCP")
        return out


def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def state_plugins() -> Path:
    return Path(os.environ.get("MYDEVAGENT_STATE_DIR", Path.home() / ".mydevagent")) / "plugins"


def is_plugin(folder: Path) -> bool:
    return (folder / ".claude-plugin" / "plugin.json").is_file() or any((folder / k).is_dir() for k in KINDS)


def find_plugins(folder: Path, depth: int = 1) -> list[Path]:
    """Un plugin, un marketplace con i suoi plugin locali, oppure una cartella che contiene plugin."""
    if not folder.is_dir():
        return []
    if is_plugin(folder):
        return [folder]
    market = _json(folder / ".claude-plugin" / "marketplace.json")
    if market:
        sources = [p.get("source") for p in market.get("plugins", []) if isinstance(p, dict)]
        # ponytail: solo sorgenti locali ("./plugins/x"); quelle github/url si installano a parte con /plugin install
        return [p for s in sources if isinstance(s, str) for p in [(folder / s).resolve()] if is_plugin(p)]
    if depth == 0:
        return []
    return [p for d in sorted(folder.iterdir()) if d.is_dir() and not d.name.startswith(".")
            for p in find_plugins(d, depth - 1)]


def claude_code_plugins() -> list[Path]:
    """I plugin attivi installati in Claude Code (formato v1 e v2 di installed_plugins.json)."""
    base = Path.home() / ".claude"
    enabled = _json(base / "settings.json").get("enabledPlugins") or {}
    out = []
    for key, entries in (_json(base / "plugins" / "installed_plugins.json").get("plugins") or {}).items():
        if enabled.get(key) is False:
            continue
        for entry in entries if isinstance(entries, list) else [entries]:
            if isinstance(entry, dict) and entry.get("installPath"):
                out.append(Path(entry["installPath"]))
    return out


def load_plugins(root: Path) -> dict[str, Plugin]:
    """nome → plugin. A parità di nome vince il primo: progetto, utente, Claude Code, cartelle extra."""
    places = [(p, "progetto") for p in find_plugins(Path(root) / ".mydevagent" / "plugins")]
    places += [(p, "utente") for p in find_plugins(state_plugins())]
    places += [(p, "claude code") for p in claude_code_plugins() if p.is_dir()]
    for raw in os.environ.get("MYDEVAGENT_PLUGINS_DIRS", "").split(os.pathsep):
        if raw.strip():
            places += [(p, "extra") for p in find_plugins(Path(raw.strip()).expanduser())]
    found: dict[str, Plugin] = {}
    for path, source in places:
        plugin = _plugin(path, source)
        found.setdefault(plugin.name, plugin)
    return found


def _plugin(path: Path, source: str) -> Plugin:
    manifest = _json(path / ".claude-plugin" / "plugin.json")
    return Plugin(str(manifest.get("name") or path.name), path, source, manifest)


# ------------------------------------------------------------ installazione
def install(spec: str) -> list[Plugin]:
    """Da una cartella locale, un URL git o `utente/repo` di GitHub (come `/plugin marketplace add`)."""
    base = state_plugins()
    base.mkdir(parents=True, exist_ok=True)
    local = Path(spec).expanduser()
    if local.is_dir():
        dest = base / local.resolve().name
    else:
        url = spec if ("://" in spec or spec.startswith("git@")) else f"https://github.com/{spec.strip('/')}"
        dest = base / url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    if dest.exists():
        raise ValueError(f"{dest.name} è già installato (/plugin update {dest.name})")
    if local.is_dir():
        shutil.copytree(local, dest, ignore=shutil.ignore_patterns(".git"))
    else:
        _git(["clone", "--depth", "1", url, str(dest)])
    found = find_plugins(dest)
    if not found:
        remove_folder(dest)
        raise ValueError("nessun plugin trovato: serve .claude-plugin/plugin.json o una cartella "
                         "commands/, skills/ o agents/")
    return [_plugin(p, "utente") for p in found]


def folder_of(plugin: Plugin) -> Path | None:
    """La cartella scaricata con /plugin install che contiene il plugin (un marketplace ne contiene più d'uno)."""
    base = state_plugins().resolve()
    path = plugin.path.resolve()
    if plugin.source != "utente" or not path.is_relative_to(base):
        return None
    return base / path.relative_to(base).parts[0]


def installed_folder(name: str, root: Path) -> Path:
    """Per nome del plugin oppure della cartella scaricata (per esempio `claude-code`)."""
    plugin = load_plugins(root).get(name)
    if plugin is None:
        folder = state_plugins() / name
        if Path(name).name != name or not folder.is_dir():
            raise ValueError(f"plugin sconosciuto: {name} (/plugin per l'elenco)")
        return folder.resolve()
    folder = folder_of(plugin)
    if folder is None:
        raise ValueError(f"{name} non è stato installato con /plugin install (viene da: {plugin.source})")
    return folder


def update(name: str, root: Path) -> str:
    folder = installed_folder(name, root)
    if not (folder / ".git").exists():
        raise ValueError(f"{name} è stato copiato da una cartella: reinstallalo per aggiornarlo")
    return _git(["-C", str(folder), "pull", "--ff-only"]).strip()


def remove(name: str, root: Path) -> Path:
    folder = installed_folder(name, root)
    others = [p.name for p in load_plugins(root).values() if p.name != name and folder_of(p) == folder]
    if others and name != folder.name:
        raise ValueError(f"{name} è arrivato con altri {len(others)} plugin nella cartella {folder.name}: "
                         f"/plugin remove {folder.name} li toglie tutti")
    remove_folder(folder)
    return folder


def remove_folder(folder: Path) -> None:
    def force(func, path, _exc):  # su Windows i file di .git sono in sola lettura
        os.chmod(path, stat.S_IWRITE)
        func(path)

    shutil.rmtree(folder, **({"onexc": force} if sys.version_info >= (3, 12) else {"onerror": force}))


def _git(args: list[str]) -> str:
    try:
        done = subprocess.run(["git", *args], capture_output=True, text=True, timeout=300,
                              env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})  # niente attese di password
    except FileNotFoundError as exc:
        raise ValueError("serve git installato (https://git-scm.com)") from exc
    if done.returncode:
        out = (done.stderr or done.stdout).strip()
        raise ValueError(out.splitlines()[-1] if out else f"git {args[0]} non riuscito")
    return done.stdout
