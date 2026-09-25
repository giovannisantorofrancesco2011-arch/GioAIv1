"""Hook nel formato di Claude Code: comandi che partono da soli a certi momenti del lavoro dell'agente.

    {"hooks": {"PostToolUse": [{"matcher": "Edit|Write",
                                "hooks": [{"type": "command", "command": "ruff format ."}]}]}}

Dove: `~/.claude/settings.json`, `~/.mydevagent/settings.json`, i plugin (`hooks/hooks.json`) e, solo dopo
che hai detto sì una volta, quelli del progetto (`.claude/settings.json`, `.claude/settings.local.json`,
`.mydevagent/settings.json`, plugin in `.mydevagent/plugins`): un repository scaricato non può eseguire
comandi sul tuo PC senza chiedertelo.

Eventi: PreToolUse (può bloccare un tool), PostToolUse, UserPromptSubmit (può bloccare la richiesta o
aggiungere contesto), Stop (può chiedere all'agente di continuare), SessionStart (aggiunge contesto),
SubagentStop. Il comando riceve il JSON dell'evento su stdin; exit code 2 = blocca, e stderr spiega perché.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .plugins import load_plugins

EVENTS = ("PreToolUse", "PostToolUse", "UserPromptSubmit", "Stop", "SubagentStop", "SessionStart")
TOOL_EVENTS = ("PreToolUse", "PostToolUse")
# i nomi dei tool di Claude Code, così i matcher dei plugin ("Edit|Write", "Bash") funzionano anche qui
CLAUDE_NAMES = {"bash": "Bash", "run_tests": "Bash", "edit_file": "Edit", "write_file": "Write",
                "read_file": "Read", "grep": "Grep", "list_files": "Glob", "web_search": "WebSearch",
                "todo_write": "TodoWrite", "skill": "Skill", "task": "Task"}


@dataclass
class Hook:
    event: str
    matcher: str
    command: str
    timeout: int = 60
    source: str = ""  # da dove viene: claude code · utente · progetto · plugin X
    project: bool = False  # definito dentro il progetto: serve il tuo consenso
    plugin_root: Path | None = None
    unsupported: str = ""  # perché MyDevAgent non lo esegue (resta visibile in /hooks)

    def matches(self, target: str, *names: str) -> bool:
        if self.matcher in ("", "*"):
            return True
        return any(re.fullmatch(self.matcher, n) for n in (target, *names) if n)


@dataclass
class Outcome:
    blocked: bool = False
    reason: str = ""  # per il modello (per UserPromptSubmit: per te)
    context: str = ""  # contesto in più per il modello
    notes: list[str] = field(default_factory=list)  # da mostrare a te: errori, systemMessage

    def add(self, attr: str, text: str) -> None:
        text = text.strip()
        if text:
            setattr(self, attr, (getattr(self, attr) + "\n" + text).strip())


# ------------------------------------------------------------------ caricamento
def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def parse(config: dict, source: str, project: bool = False, plugin_root: Path | None = None) -> list[Hook]:
    out = []
    for event, groups in (config.get("hooks") or {}).items():
        for group in groups if isinstance(groups, list) else []:
            for spec in group.get("hooks", []) if isinstance(group, dict) else []:
                # ponytail: solo gli hook "command"; quelli "prompt" (valutati da un LLM) vengono ignorati
                if isinstance(spec, dict) and spec.get("type", "command") == "command" and spec.get("command"):
                    skip = [k for k in ("if", "async", "asyncRewake") if spec.get(k)]
                    unsupported = ("non ancora supportati: " + ", ".join(skip)) if skip else (
                        "" if event in EVENTS else "evento non ancora supportato")
                    out.append(Hook(event, str(group.get("matcher") or ""), str(spec["command"]),
                                    int(spec.get("timeout") or 60), source, project, plugin_root, unsupported))
    return out


def _plugin_configs(plugin) -> list[dict]:
    """hooks/hooks.json più il campo "hooks" del plugin.json (un percorso, una lista o gli hook stessi)."""
    declared = plugin.manifest.get("hooks")
    items = declared if isinstance(declared, list) else [declared] if declared else []
    default = plugin.path / "hooks" / "hooks.json"
    configs = [_json(default)]
    for item in items:
        if isinstance(item, dict):
            configs.append(item if "hooks" in item else {"hooks": item})
        elif isinstance(item, str) and (plugin.path / item).resolve() != default.resolve():
            configs.append(_json(plugin.path / item))
    return configs


def all_hooks(root: Path) -> list[Hook]:
    """Tutti gli hook trovati, compresi quelli del progetto non ancora autorizzati."""
    root = Path(root)
    state = Path(os.environ.get("MYDEVAGENT_STATE_DIR", Path.home() / ".mydevagent"))
    settings = [(Path.home() / ".claude" / "settings.json", "claude code", False),
                (state / "settings.json", "utente", False),
                (root / ".claude" / "settings.json", "progetto", True),
                (root / ".claude" / "settings.local.json", "progetto", True),
                (root / ".mydevagent" / "settings.json", "progetto", True)]
    configs = [(_json(path), source, project) for path, source, project in settings]
    if any(c.get("disableAllHooks") for c, _, _ in configs):
        return []
    hooks = [h for config, source, project in configs for h in parse(config, source, project)]
    for plugin in load_plugins(root).values():
        for config in _plugin_configs(plugin):
            hooks += parse(config, f"plugin {plugin.name}", plugin.source == "progetto", plugin.path)
    return hooks


def _trust_file() -> Path:
    return Path(os.environ.get("MYDEVAGENT_STATE_DIR", Path.home() / ".mydevagent")) / "trusted_hooks.json"


def fingerprint(hooks: list[Hook]) -> str:
    return hashlib.sha256("\n".join(sorted(f"{h.event}|{h.matcher}|{h.command}" for h in hooks)).encode()).hexdigest()


def untrusted(root: Path) -> list[Hook]:
    """Gli hook del progetto che aspettano il tuo sì (di nuovo, se sono cambiati da allora)."""
    project = [h for h in all_hooks(root) if h.project]
    if not project or _json(_trust_file()).get(str(Path(root).resolve())) == fingerprint(project):
        return []
    return project


def trust(root: Path) -> None:
    path = _trust_file()
    data = _json(path)
    data[str(Path(root).resolve())] = fingerprint([h for h in all_hooks(root) if h.project])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_hooks(root: Path) -> list[Hook]:
    """Gli hook attivi: quelli del progetto solo se li hai autorizzati."""
    pending = untrusted(root)
    return [h for h in all_hooks(root) if not (h.project and pending)]


# -------------------------------------------------------------------- esecuzione
def _shell(command: str) -> list[str] | str:
    """Su Windows gli hook dei plugin sono scritti per bash: usa quello di Git se c'è (come Claude Code)."""
    if sys.platform != "win32":
        return command
    git = shutil.which("git")
    bash = Path(git).resolve().parent.parent / "bin" / "bash.exe" if git else None
    return [str(bash), "-c", command] if bash and bash.is_file() else command


class Hooks:
    def __init__(self, root: Path, hooks: list[Hook] | None = None, session_id: str = "") -> None:
        self.root = Path(root).resolve()
        self.hooks = load_hooks(self.root) if hooks is None else hooks
        self.session_id = session_id or uuid.uuid4().hex
        self.mode = "default"
        self.session_context = ""  # quello che gli hook SessionStart hanno aggiunto

    def start(self, source: str = "startup") -> Outcome:
        outcome = self.run("SessionStart", target=source, payload={"source": source})
        self.session_context = outcome.context
        return outcome

    def __bool__(self) -> bool:
        return bool(self.hooks)

    def run(self, event: str, *, target: str = "", payload: dict[str, Any] | None = None) -> Outcome:
        """Esegue gli hook dell'evento. `target` è il tool (o la fonte, per SessionStart) da confrontare col matcher."""
        outcome = Outcome()
        names = [CLAUDE_NAMES.get(target, "")] if event in TOOL_EVENTS else []
        data = {"session_id": self.session_id, "transcript_path": "", "cwd": str(self.root),
                "hook_event_name": event, "permission_mode": self.mode, **(payload or {})}
        for hook in self.hooks:
            if hook.event == event and not hook.unsupported and hook.matches(target, *names):
                self._run_one(hook, data, outcome)
        return outcome

    def tool_payload(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        tool_input = dict(args)
        if "path" in args:  # come Claude Code: percorso assoluto in file_path
            tool_input["file_path"] = str((self.root / str(args["path"])).resolve())
        return {"tool_name": CLAUDE_NAMES.get(tool, tool), "tool_input": tool_input}

    def _run_one(self, hook: Hook, data: dict[str, Any], outcome: Outcome) -> None:
        env = {**os.environ, "CLAUDE_PROJECT_DIR": str(self.root), "MYDEVAGENT": "1"}
        command = hook.command.replace("${CLAUDE_PROJECT_DIR}", str(self.root))
        if hook.plugin_root:
            env["CLAUDE_PLUGIN_ROOT"] = str(hook.plugin_root)
            command = command.replace("${CLAUDE_PLUGIN_ROOT}", str(hook.plugin_root))
        label = hook.command if len(hook.command) <= 60 else hook.command[:57] + "…"
        args = _shell(command)
        try:
            proc = subprocess.run(args, shell=isinstance(args, str), input=json.dumps(data), capture_output=True,
                                  text=True, timeout=hook.timeout, cwd=self.root, env=env, encoding="utf-8",
                                  errors="replace")
        except subprocess.TimeoutExpired:
            outcome.notes.append(f"hook «{label}» fermato dopo {hook.timeout}s")
            return
        except OSError as exc:
            outcome.notes.append(f"hook «{label}» non avviato: {exc}")
            return
        if proc.returncode == 2:
            outcome.blocked = True
            outcome.add("reason", proc.stderr or f"bloccato da «{label}»")
            return
        if proc.returncode != 0:
            outcome.notes.append(f"hook «{label}» fallito (exit {proc.returncode}): {proc.stderr.strip()[:200]}")
            return
        out = proc.stdout.strip()
        try:
            result = json.loads(out) if out.startswith("{") else None
        except ValueError:
            result = None
        if not isinstance(result, dict):
            if data["hook_event_name"] in ("UserPromptSubmit", "SessionStart"):
                outcome.add("context", out)
            return
        specific = result.get("hookSpecificOutput") or {}
        if result.get("continue") is False:
            outcome.blocked = True
            outcome.add("reason", str(result.get("stopReason") or f"fermato da «{label}»"))
        if result.get("decision") == "block":
            outcome.blocked = True
            outcome.add("reason", str(result.get("reason") or f"bloccato da «{label}»"))
        # ponytail: "allow"/"ask" non scavalcano i permessi di MyDevAgent; conta solo "deny"
        if specific.get("permissionDecision") == "deny":
            outcome.blocked = True
            outcome.add("reason", str(specific.get("permissionDecisionReason") or f"negato da «{label}»"))
        outcome.add("context", str(specific.get("additionalContext") or ""))
        if result.get("systemMessage"):
            outcome.notes.append(str(result["systemMessage"]))
