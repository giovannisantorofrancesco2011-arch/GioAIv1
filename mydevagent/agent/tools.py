"""Tool dell'agente: leggere, cercare, modificare, eseguire. Ogni azione passa da permessi e checkpoint."""

from __future__ import annotations

import difflib
import json
import os
import re
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..tools.filesystem import IGNORED_DIRS, Workspace, WorkspaceError
from .checkpoints import CheckpointStore
from .permissions import EDIT_TOOLS, ApprovalRequest, Approver, PermissionPolicy, is_dangerous

MAX_RESULT_CHARS = 8000
DEFAULT_READ_LINES = 250
EventHandler = Callable[[dict[str, Any]], None]

SPECS: list[dict[str, Any]] = [
    {"name": "read_file", "description": "Read a text file with line numbers. Use offset/limit for big files.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "offset": {"type": "integer", "description": "first line (1-based)"},
         "limit": {"type": "integer"}}, "required": ["path"]}},
    {"name": "list_files", "description": "List project files (recursive). Optional glob pattern like '*.py'.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "pattern": {"type": "string"}}}},
    {"name": "grep", "description": "Search a regex in project files. Returns path:line: text.",
     "parameters": {"type": "object", "properties": {
         "pattern": {"type": "string"}, "glob": {"type": "string"}}, "required": ["pattern"]}},
    {"name": "edit_file", "description": "Replace an exact snippet in a file. old_string must match the file "
     "exactly (copy it from read_file without line numbers) and be unique unless replace_all is true.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "old_string": {"type": "string"}, "new_string": {"type": "string"},
         "replace_all": {"type": "boolean"}}, "required": ["path", "old_string", "new_string"]}},
    {"name": "write_file", "description": "Create a new file or fully overwrite a small file.",
     "parameters": {"type": "object", "properties": {
         "path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "bash", "description": "Run a shell command in the project directory (build, tests, git, tools).",
     "parameters": {"type": "object", "properties": {
         "command": {"type": "string"}, "timeout": {"type": "integer"}}, "required": ["command"]}},
    {"name": "run_tests", "description": "Run the project's test suite (auto-detected) and return the result.",
     "parameters": {"type": "object", "properties": {"command": {"type": "string",
                    "description": "optional explicit test command"}}}},
    {"name": "todo_write", "description": "Write the task checklist. Use it for multi-step tasks and keep it "
     "updated: status is pending, in_progress or completed.",
     "parameters": {"type": "object", "properties": {"todos": {"type": "array", "items": {
         "type": "object", "properties": {"content": {"type": "string"}, "status": {"type": "string"}}}}},
         "required": ["todos"]}},
    {"name": "web_search", "description": "Search the web for up-to-date docs, versions, errors (only online).",
     "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]
SPEC_BY_NAME = {s["name"]: s for s in SPECS}


def truncate_middle(text: str, limit: int = MAX_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    head = int(limit * 0.6)
    tail = limit - head
    omitted = text[head:-tail].count("\n")
    return f"{text[:head]}\n…[{omitted} lines omitted]…\n{text[-tail:]}"


def unified_diff(old: str, new: str, path: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{path}", f"b/{path}"))


def diff_stats(diff: str) -> tuple[int, int]:
    added = sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---"))
    return added, removed


def detect_test_command(root: Path, memory: str = "") -> str | None:
    match = re.search(r"^\s*[-*]?\s*(?:test|tests)\s*:\s*`?([^`\n]+)`?", memory, re.IGNORECASE | re.MULTILINE)
    if match:
        return match.group(1).strip()
    if (root / "package.json").is_file():
        try:
            scripts = json.loads((root / "package.json").read_text(encoding="utf-8")).get("scripts", {})
            if "test" in scripts:
                return "npm test --silent"
        except ValueError:
            pass
    if (root / "go.mod").is_file():
        return "go test ./..."
    if (root / "Cargo.toml").is_file():
        return "cargo test -q"
    py_markers = ("pyproject.toml", "setup.cfg", "pytest.ini", "tox.ini", "setup.py")
    if any((root / m).is_file() for m in py_markers) or list(root.glob("test*.py")) or (root / "tests").is_dir():
        return "python -m pytest -q"
    return None


class AgentTools:
    def __init__(self, root: Path, policy: PermissionPolicy, checkpoints: CheckpointStore,
                 approver: Approver | None = None, emit: EventHandler | None = None,
                 web_search: Callable[[str], str] | None = None, memory: str = "",
                 bash_timeout: int = 120) -> None:
        self.root = Path(root).resolve()
        self.workspace = Workspace(self.root, allow_write=True)
        self.policy = policy
        self.checkpoints = checkpoints
        self.approver = approver
        self.emit = emit or (lambda _e: None)
        self.web_search_fn = web_search
        self.memory = memory
        self.bash_timeout = bash_timeout
        self.todos: list[dict[str, str]] = []
        self.changed: list[str] = []
        self.read_paths: set[str] = set()
        self.last_test: tuple[str, bool, str] | None = None  # (comando, ok, output)
        self._lock = threading.Lock()

    # ----------------------------------------------------------------- spec
    def specs(self) -> list[dict[str, Any]]:
        specs = SPECS if self.web_search_fn else [s for s in SPECS if s["name"] != "web_search"]
        if self.policy.mode == "plan":
            specs = [s for s in specs if s["name"] not in EDIT_TOOLS]
        return specs

    def openai_schemas(self) -> list[dict[str, Any]]:
        return [{"type": "function", "function": s} for s in self.specs()]

    # -------------------------------------------------------------- dispatch
    def execute(self, name: str, args: dict[str, Any]) -> str:
        handler = getattr(self, f"_t_{name}", None)
        if handler is None or name not in SPEC_BY_NAME:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(s['name'] for s in self.specs())}"
        self.emit({"type": "tool_call", "agent": "agent", "tool": name, "args": _display_args(name, args)})
        try:
            result = handler(**args)
        except TypeError as exc:
            result = f"ERROR: bad arguments for {name}: {exc}"
        except (WorkspaceError, FileNotFoundError, IsADirectoryError, UnicodeDecodeError) as exc:
            result = f"ERROR: {type(exc).__name__}: {exc}"
        except Exception as exc:  # un tool non deve mai far cadere il ciclo
            result = f"ERROR: {name} failed: {type(exc).__name__}: {exc}"
        ok = not result.startswith(("ERROR", "DENIED"))
        self.emit({"type": "tool_result", "agent": "agent", "tool": name, "ok": ok,
                   "preview": _preview(name, result)})
        return truncate_middle(result)

    # ------------------------------------------------------------- permessi
    def _authorize(self, tool: str, args: dict[str, Any], summary: str, diff: str = "") -> str | None:
        """None = consentito; altrimenti il messaggio da restituire al modello."""
        decision = self.policy.decide(tool, args)
        if decision.action == "allow":
            return None
        if decision.action == "deny":
            return f"DENIED: {decision.reason}"
        if self.approver is None:
            return "DENIED: this action needs user approval, which is not available in this context."
        command = str(args.get("command", ""))
        request = ApprovalRequest(tool=tool, args=args, summary=summary, diff=diff,
                                  dangerous=bool(command) and is_dangerous(command))
        with self._lock:
            answer, feedback = self.approver(request)
        if answer == "always":
            self.policy.remember(self.policy.rule_for(tool, args))
            return None
        if answer == "yes":
            return None
        return "DENIED by the user." + (f" User says: {feedback}" if feedback else
                                         " Ask what to do differently or try another approach.")

    # ------------------------------------------------------------------ tool
    def _rel(self, path: str) -> tuple[str, Path]:
        target = self.workspace.resolve(path)
        return target.relative_to(self.root).as_posix(), target

    def _t_read_file(self, path: str, offset: int = 1, limit: int = DEFAULT_READ_LINES) -> str:
        rel, target = self._rel(path)
        if self.workspace.is_secret(target):
            return f"ERROR: {rel} looks like a secrets file; not reading it."
        if target.is_dir():
            return f"ERROR: {rel} is a directory; use list_files."
        if not target.is_file():
            return f"ERROR: file not found: {rel}"
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
        self.read_paths.add(rel)
        start = max(1, int(offset))
        end = min(len(lines), start + max(1, int(limit)) - 1)
        body = "\n".join(f"{n:>5}→{lines[n - 1]}" for n in range(start, end + 1))
        more = f"\n… {len(lines) - end} more lines (use offset={end + 1})" if end < len(lines) else ""
        return f"{rel} ({len(lines)} lines)\n{body}{more}" if lines else f"{rel} (empty file)"

    def _t_list_files(self, path: str = ".", pattern: str = "*") -> str:
        base = self.workspace.resolve(path)
        out = []
        for item in sorted(base.rglob(pattern)):
            rel = item.relative_to(self.root)
            if any(part in IGNORED_DIRS for part in rel.parts) or not item.is_file():
                continue
            out.append(rel.as_posix())
            if len(out) >= 400:
                out.append("… (truncated, use a narrower path or pattern)")
                break
        return "\n".join(out) or "no files"

    def _t_grep(self, pattern: str, glob: str = "*") -> str:
        try:
            re.compile(pattern)
        except re.error as exc:
            return f"ERROR: invalid regex: {exc}"
        return self.workspace.grep(pattern, glob, limit=80)

    def _t_edit_file(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        rel, target = self._rel(path)
        if self.workspace.is_secret(target):
            return f"ERROR: refusing to edit secrets file {rel}"
        if not target.is_file():
            return f"ERROR: file not found: {rel}. Use write_file to create it."
        old_text = target.read_text(encoding="utf-8", errors="replace")
        if old_string == new_string:
            return "ERROR: old_string and new_string are identical."
        new_text, error = apply_edit(old_text, old_string, new_string, replace_all)
        if error:
            return f"ERROR: {error}"
        return self._commit_write("edit_file", rel, target, old_text, new_text,
                                  {"path": rel, "old_string": old_string, "new_string": new_string})

    def _t_write_file(self, path: str, content: str) -> str:
        rel, target = self._rel(path)
        if self.workspace.is_secret(target):
            return f"ERROR: refusing to write secrets file {rel}"
        old_text = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        if target.is_file() and old_text == content:
            return f"{rel} already has this content."
        return self._commit_write("write_file", rel, target, old_text, content, {"path": rel, "content": content},
                                  created=not target.exists())

    def _commit_write(self, tool: str, rel: str, target: Path, old: str, new: str, args: dict[str, Any],
                      created: bool = False) -> str:
        diff = unified_diff(old, new, rel)
        action = "Create" if created else "Update"
        denied = self._authorize(tool, args, f"{action}({rel})", diff)
        if denied:
            return denied
        self.checkpoints.before_write(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new, encoding="utf-8")
        if rel not in self.changed:
            self.changed.append(rel)
        added, removed = diff_stats(diff)
        self.emit({"type": "diff", "path": rel, "action": action, "diff": diff, "added": added, "removed": removed})
        return f"{action.lower()}d {rel} (+{added} -{removed})"

    def _t_bash(self, command: str, timeout: int | None = None) -> str:
        denied = self._authorize("bash", {"command": command}, f"Bash({command})")
        if denied:
            return denied
        return self._run(command, timeout or self.bash_timeout)

    def _t_run_tests(self, command: str | None = None) -> str:
        command = command or detect_test_command(self.root, self.memory)
        if not command:
            return "NO TESTS: no test suite detected. Tell the user how to verify manually."
        denied = self._authorize("run_tests", {"command": command}, f"Test({command})")
        if denied:
            return denied
        result = self._run(command, max(self.bash_timeout, 300))
        ok = result.startswith("exit code 0")
        self.last_test = (command, ok, result)
        self.emit({"type": "tests", "command": command, "ok": ok})
        if ok and self.changed:  # aiuta i modelli piccoli a capire quando fermarsi
            result += ("\n\nAll tests pass. If the requested change is complete, STOP calling tools and give "
                       "your short final answer now.")
        return result

    def _run(self, command: str, timeout: int) -> str:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CI": "1", "NO_COLOR": "1"}
        try:
            proc = subprocess.run(command, shell=True, cwd=self.root, capture_output=True, text=True,
                                  timeout=timeout, env=env, stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired as exc:
            out = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            return f"TIMEOUT after {timeout}s\n{out[-3000:]}"
        output = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
        return f"exit code {proc.returncode}\n{output}"

    def _t_todo_write(self, todos: list[dict[str, Any]]) -> str:
        clean = []
        for item in todos:
            status = str(item.get("status", "pending")).lower()
            clean.append({"content": str(item.get("content", "")).strip(),
                          "status": status if status in ("pending", "in_progress", "completed") else "pending"})
        self.todos = [t for t in clean if t["content"]]
        self.emit({"type": "todo", "todos": self.todos})
        done = sum(t["status"] == "completed" for t in self.todos)
        return f"todo list updated ({done}/{len(self.todos)} completed)"

    def _t_web_search(self, query: str) -> str:
        if not self.web_search_fn:
            return "ERROR: web search not available."
        return self.web_search_fn(query)


def apply_edit(text: str, old: str, new: str, replace_all: bool = False) -> tuple[str, str | None]:
    """Sostituzione esatta, poi tollerante sugli spazi a fine riga, poi sull'indentazione."""
    if not old:
        return text, "old_string is empty; use write_file to create a file."
    count = text.count(old)
    if count == 1 or (count > 1 and replace_all):
        return text.replace(old, new) if replace_all else text.replace(old, new, 1), None
    if count > 1:
        return text, (f"old_string matches {count} places. Add surrounding lines to make it unique, "
                      "or set replace_all=true.")
    # tolleranza: confronto riga per riga ignorando gli spazi finali e poi l'indentazione
    lines = text.splitlines(keepends=True)
    old_lines = old.strip("\n").splitlines()
    for normalize in (str.rstrip, str.strip):
        target = [normalize(line) for line in old_lines]
        hits = [i for i in range(len(lines) - len(target) + 1)
                if [normalize(line.rstrip("\n")) for line in lines[i:i + len(target)]] == target]
        if len(hits) == 1:
            i = hits[0]
            original = "".join(lines[i:i + len(target)])
            replacement = new.strip("\n")
            if normalize is str.strip:  # reindenta il nuovo testo come l'originale
                replacement = _reindent(replacement, _indent(lines[i]), _indent(old_lines[0]))
            if original.endswith("\n") and not replacement.endswith("\n"):
                replacement += "\n"
            return "".join(lines[:i]) + replacement + "".join(lines[i + len(target):]), None
        if len(hits) > 1:
            return text, f"old_string (ignoring whitespace) matches {len(hits)} places; add more context."
    close = difflib.get_close_matches(old_lines[0].strip() if old_lines else "",
                                      [line.strip() for line in lines], n=3, cutoff=0.6)
    hint = ("\nSimilar lines in the file:\n" + "\n".join(f"  {c}" for c in close)) if close else ""
    return text, f"old_string not found. Re-read the file with read_file and copy the text exactly.{hint}"


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _reindent(text: str, file_indent: str, given_indent: str) -> str:
    out = []
    for line in text.splitlines():
        if line.startswith(given_indent):
            line = file_indent + line[len(given_indent):]
        elif line.strip():
            line = file_indent + line.lstrip()
        out.append(line)
    return "\n".join(out)


def _display_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name in ("edit_file", "write_file"):
        return {"path": args.get("path", "")}
    if name == "todo_write":
        return {"items": len(args.get("todos", []) or [])}
    return args


def _preview(name: str, result: str) -> str:
    if name == "read_file" and not result.startswith("ERROR"):
        return result.split("\n", 1)[0]
    if name in ("bash", "run_tests"):
        lines = [line for line in result.splitlines() if line.strip() and not line.startswith("All tests pass")]
        picked = lines[:1] + (lines[-1:] if len(lines) > 1 else [])
        return " · ".join(picked)[:200]
    return result[:200]
