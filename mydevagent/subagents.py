"""Sotto-agenti come in Claude Code: un file Markdown con nome, descrizione e prompt di sistema.

    ---
    name: code-reviewer
    description: Rivede il codice appena modificato. Usalo dopo ogni modifica importante.
    tools: Read, Grep, Glob        # facoltativo: senza, ha tutti i tool
    model: haiku                   # facoltativo: haiku usa il modello veloce
    ---
    Sei un revisore severo…

L'agente principale li chiama con il tool `task`: il sotto-agente lavora in un contesto tutto suo (non
vede la conversazione), con i suoi tool e i soliti permessi, e restituisce solo il resoconto finale.
Cartelle: `.mydevagent/agents` e `.claude/agents` del progetto, `~/.mydevagent/agents`, `~/.claude/agents`
e gli `agents/` dei plugin.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .plugins import load_plugins
from .skills import short, split_frontmatter

# i tool di Claude Code → quelli di MyDevAgent
TOOL_NAMES = {"Read": ["read_file"], "Grep": ["grep"], "Glob": ["list_files"], "LS": ["list_files"],
              "Bash": ["bash", "run_tests"], "Edit": ["edit_file"], "MultiEdit": ["edit_file"],
              "Write": ["write_file"], "NotebookEdit": ["edit_file"], "NotebookRead": ["read_file"],
              "WebSearch": ["web_search"], "WebFetch": ["web_search"], "TodoWrite": ["todo_write"],
              "Skill": ["skill"]}


@dataclass
class SubAgent:
    name: str
    description: str
    prompt: str
    source: str
    tools: list[str] | None = None  # None = tutti
    model: str = ""

    @property
    def tier(self) -> str:
        return "fast" if self.model.lower() in ("haiku", "fast") else "main"

    def allowed(self) -> set[str] | None:
        if not self.tools:
            return None
        out: set[str] = set()
        for tool in self.tools:
            tool = tool.split("(", 1)[0]  # Bash(git:*) → Bash
            out.update(["mcp"] if tool.startswith("mcp__") else TOOL_NAMES.get(tool, [tool]))
        return out


def parse_tools(value: str) -> list[str] | None:
    """`Read, Grep` oppure `["Read", "Grep"]` (entrambi si trovano nei plugin)."""
    return [t.strip(" '\"") for t in value.strip().strip("[]").split(",") if t.strip(" '\"")] or None


def agent_dirs(root: Path) -> list[tuple[Path, str]]:
    home = Path.home()
    state = Path(os.environ.get("MYDEVAGENT_STATE_DIR", home / ".mydevagent"))
    dirs = [(root / ".mydevagent" / "agents", "progetto"), (root / ".claude" / "agents", "progetto"),
            (state / "agents", "utente"), (home / ".claude" / "agents", "utente")]
    for plugin in load_plugins(root).values():
        dirs += [(d, f"plugin {plugin.name}") for d in plugin.dirs("agents")]
    return dirs


def load_subagents(root: Path) -> dict[str, SubAgent]:
    """nome → sotto-agente. A parità di nome vince la cartella più specifica (il progetto)."""
    found: dict[str, SubAgent] = {}
    for folder, source in agent_dirs(Path(root)):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob("*.md")):
            try:
                meta, body = split_frontmatter(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            name = re.sub(r"[^\w-]+", "-", meta.get("name") or path.stem).strip("-").lower()
            if not name or name in found or not body.strip():
                continue
            tools = parse_tools(meta.get("tools", ""))
            found[name] = SubAgent(name, meta.get("description") or name, body.strip(), source, tools,
                                   meta.get("model", ""))
    return found


def subagents_prompt(agents: dict[str, SubAgent]) -> str:
    if not agents:
        return ""
    lines = "\n".join(f"- {a.name}: {short(a.description)}" for a in agents.values())
    return ("# Sub-agents\nFor a self-contained job that matches one of these agents, delegate it with the `task` "
            "tool: the agent works in its own context and returns only its report. Give it a complete prompt "
            "(it cannot see this conversation).\n" + lines)
