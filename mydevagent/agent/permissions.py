"""Permessi dell'agente, come in Claude Code: ask · auto-edit · plan · auto."""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MODES = ("ask", "auto-edit", "plan", "auto")
MODE_LABELS = {
    "ask": "chiede conferma",
    "auto-edit": "modifiche automatiche",
    "plan": "piano (sola lettura)",
    "auto": "tutto automatico",
}
READ_TOOLS = {"read_file", "list_files", "grep", "web_search", "todo_write", "git_diff", "skill"}
EDIT_TOOLS = {"edit_file", "write_file"}
EXEC_TOOLS = {"bash", "run_tests"}

# comandi che chiedono SEMPRE conferma, anche in modalità auto
DANGEROUS = [
    r"\brm\s+(-\w*r\w*f|-\w*f\w*r)\b", r"\brm\s+-r\b", r"\bsudo\b", r"\bmkfs\b", r"\bdd\s+if=",
    r"git\s+push\b.*(--force|-f\b)", r"git\s+reset\s+--hard", r"git\s+clean\s+-\w*f",
    r"(curl|wget)[^|]*\|\s*(sh|bash|zsh|python)", r">\s*/dev/sd", r"\bchmod\s+-R\s+777", r":\(\)\s*\{",
    r"\bshutdown\b", r"\breboot\b", r"Remove-Item\b.*-Recurse", r"\bformat\s+[a-z]:",
]
# comandi di sola lettura consentiti anche in modalità plan
READ_ONLY_COMMANDS = [r"^(ls|dir|cat|type|head|tail|wc|pwd|echo|tree|find|rg|grep|which|where)\b",
                      r"^git\s+(status|diff|log|show|branch|blame)\b"]


@dataclass
class Decision:
    action: str  # allow | ask | deny
    reason: str = ""


@dataclass
class ApprovalRequest:
    tool: str
    args: dict[str, Any]
    summary: str
    diff: str = ""
    dangerous: bool = False


# risposta: ("yes" | "always" | "no", feedback)
Approver = Callable[[ApprovalRequest], tuple[str, str]]


def is_dangerous(command: str) -> bool:
    return any(re.search(p, command, re.IGNORECASE) for p in DANGEROUS)


def is_read_only(command: str) -> bool:
    if re.search(r"[;&|>]", command):
        return False
    return any(re.search(p, command.strip(), re.IGNORECASE) for p in READ_ONLY_COMMANDS)


@dataclass
class PermissionPolicy:
    mode: str = "ask"
    root: Path | None = None
    allow_rules: list[str] = field(default_factory=list)  # es. "bash:pytest*", "edit:src/*"

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"modalità sconosciuta: {self.mode} ({', '.join(MODES)})")
        self.allow_rules = list(self.allow_rules) + self._load_rules()

    # --------------------------------------------------------- persistenza
    @property
    def settings_file(self) -> Path | None:
        return self.root / ".mydevagent" / "settings.json" if self.root else None

    def _load_rules(self) -> list[str]:
        path = self.settings_file
        if path and path.is_file():
            try:
                return list(json.loads(path.read_text(encoding="utf-8")).get("allow", []))
            except (ValueError, OSError):
                return []
        return []

    def remember(self, rule: str, persist: bool = True) -> None:
        if rule not in self.allow_rules:
            self.allow_rules.append(rule)
        path = self.settings_file
        if persist and path:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
            data["allow"] = sorted(set(data.get("allow", [])) | {rule})
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def rule_for(self, tool: str, args: dict[str, Any]) -> str:
        if tool in EDIT_TOOLS:
            return f"edit:{args.get('path', '')}"
        if tool == "bash":
            first = str(args.get("command", "")).split()
            return f"bash:{first[0]}*" if first else "bash:"
        return f"{tool}:*"

    def _allowed_by_rule(self, tool: str, args: dict[str, Any]) -> bool:
        if tool in EDIT_TOOLS:
            target = f"edit:{args.get('path', '')}"
        elif tool == "bash":
            target = f"bash:{args.get('command', '')}"
        else:
            target = f"{tool}:"
        return any(fnmatch.fnmatch(target, rule) for rule in self.allow_rules)

    # ------------------------------------------------------------ decisione
    def decide(self, tool: str, args: dict[str, Any]) -> Decision:
        if tool in READ_TOOLS:
            return Decision("allow")
        command = str(args.get("command", "")) if tool == "bash" else ""
        if command and is_dangerous(command):
            return Decision("ask", "comando potenzialmente distruttivo")
        if self.mode == "plan":
            if tool == "bash" and is_read_only(command):
                return Decision("allow")
            return Decision("deny", "plan mode: read-only. Describe the plan instead of changing files.")
        if self.mode == "auto":
            return Decision("allow")
        if tool in EDIT_TOOLS:
            if self.mode == "auto-edit" or self._allowed_by_rule(tool, args):
                return Decision("allow")
            return Decision("ask")
        if tool in EXEC_TOOLS:
            if tool == "bash" and (is_read_only(command) or self._allowed_by_rule(tool, args)):
                return Decision("allow")
            if tool == "run_tests" and self._allowed_by_rule(tool, args):
                return Decision("allow")
            return Decision("ask")
        return Decision("ask")

    def next_mode(self) -> str:
        cycle = ["ask", "auto-edit", "plan"]
        self.mode = cycle[(cycle.index(self.mode) + 1) % len(cycle)] if self.mode in cycle else "ask"
        return self.mode
