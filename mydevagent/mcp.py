"""Server MCP (Model Context Protocol), configurati come in Claude Code: GitHub, database, browser…

    {"mcpServers": {
        "github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"],
                   "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"}},
        "docs": {"type": "http", "url": "https://esempio.com/mcp", "headers": {"Authorization": "Bearer ${TOKEN}"}}}}

Dove: `.mcp.json` del progetto (solo dopo il tuo sì, come gli hook), `~/.claude.json` (i server che usi con
Claude Code, anche quelli del singolo progetto), `~/.mydevagent/mcp.json` e i plugin (`.mcp.json`).

Client minimo JSON-RPC su stdio e su HTTP ("streamable HTTP", risposte JSON o SSE). All'agente arriva un
solo tool, `mcp`: senza `tool` elenca gli strumenti di un server con i loro argomenti, con `tool` lo usa.
Così anche con server da 50 strumenti il prompt resta piccolo per i modelli locali.
"""

from __future__ import annotations

import itertools
import json
import os
import re
import shutil
import subprocess
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import trust
from .plugins import load_plugins

PROTOCOL_VERSION = "2025-06-18"
TIMEOUT = 60
ENV_RE = re.compile(r"\$\{(\w+)(?::-([^}]*))?\}")


class McpError(RuntimeError):
    pass


@dataclass
class ServerConfig:
    name: str
    config: dict[str, Any]
    source: str  # progetto · claude code · utente · plugin X
    project: bool = False  # definito dentro il progetto: serve il tuo sì
    plugin_root: Path | None = None

    @property
    def kind(self) -> str:
        return str(self.config.get("type") or ("http" if self.config.get("url") else "stdio"))

    def describe(self) -> str:
        if self.kind == "stdio":
            return " ".join([str(self.config.get("command", ""))] + [str(a) for a in self.config.get("args", [])])
        return str(self.config.get("url", ""))


# ------------------------------------------------------------------ configurazione
def _json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def expand(value: Any, extra: dict[str, str] | None = None) -> Any:
    """`${VAR}` e `${VAR:-predefinito}` come in Claude Code, anche dentro liste e dizionari."""
    env = {**os.environ, **(extra or {})}
    if isinstance(value, str):
        return ENV_RE.sub(lambda m: env.get(m[1]) or (m[2] or ""), value)
    if isinstance(value, list):
        return [expand(v, extra) for v in value]
    if isinstance(value, dict):
        return {k: expand(v, extra) for k, v in value.items()}
    return value


def _servers(data: dict, flat: bool = False) -> dict[str, dict]:
    """La sezione mcpServers; con `flat` anche i server scritti direttamente (come in alcuni plugin)."""
    servers = data.get("mcpServers", data if flat else {})
    if not isinstance(servers, dict):
        return {}
    return {k: v for k, v in servers.items() if isinstance(v, dict) and (v.get("command") or v.get("url"))}


def server_configs(root: Path) -> dict[str, ServerConfig]:
    """nome → configurazione. A parità di nome vince il primo: locale, progetto, utente, MyDevAgent, plugin."""
    root = Path(root).resolve()
    claude = _json(Path.home() / ".claude.json")
    local = (claude.get("projects") or {}).get(str(root)) or {}
    state = Path(os.environ.get("MYDEVAGENT_STATE_DIR", Path.home() / ".mydevagent"))
    places = [(_servers(local), "claude code", False, None),
              (_servers(_json(root / ".mcp.json")), "progetto", True, None),
              (_servers(claude), "claude code", False, None),
              (_servers(_json(state / "mcp.json")), "utente", False, None)]
    for plugin in load_plugins(root).values():
        declared = plugin.manifest.get("mcpServers")
        data = _json(plugin.path / declared) if isinstance(declared, str) else declared or {}
        data = {**_servers(_json(plugin.path / ".mcp.json"), flat=True), **_servers(data, flat=True)}
        places.append((data, f"plugin {plugin.name}", plugin.source == "progetto", plugin.path))
    found: dict[str, ServerConfig] = {}
    for servers, source, project, plugin_root in places:
        for name, config in servers.items():
            found.setdefault(name, ServerConfig(name, config, source, project, plugin_root))
    return found


def _items(configs: dict[str, ServerConfig]) -> list[str]:
    return [f"{c.name}|{json.dumps(c.config, sort_keys=True)}" for c in configs.values() if c.project]


def untrusted(root: Path) -> list[ServerConfig]:
    configs = server_configs(root)
    return [] if trust.is_trusted(root, "mcp", _items(configs)) else [c for c in configs.values() if c.project]


def allow(root: Path) -> None:
    trust.trust(root, "mcp", _items(server_configs(root)))


# ------------------------------------------------------------------ trasporti
class StdioTransport:
    """Un processo che parla JSON-RPC, un messaggio per riga, su stdin/stdout."""

    def __init__(self, command: list[str], env: dict[str, str], cwd: Path) -> None:
        exe = shutil.which(command[0]) or command[0]  # su Windows trova npx.cmd, uvx.exe…
        self.proc = subprocess.Popen([exe, *command[1:]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, cwd=cwd, env={**os.environ, **env}, text=True,
                                     encoding="utf-8", errors="replace", bufsize=1)
        self.pending: dict[int, dict] = {}
        self.cond = threading.Condition()
        self.stderr: deque[str] = deque(maxlen=20)
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=lambda: self.stderr.extend(self.proc.stderr), daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            try:
                msg = json.loads(line)
            except ValueError:
                continue  # righe di log su stdout: le ignoro
            if not isinstance(msg, dict):
                continue
            if "method" in msg and "id" in msg:  # richieste del server (ping, sampling…)
                reply = {"result": {}} if msg["method"] == "ping" else {
                    "error": {"code": -32601, "message": "method not supported by MyDevAgent"}}
                self.send({"jsonrpc": "2.0", "id": msg["id"], **reply})
            elif "id" in msg:
                with self.cond:
                    self.pending[msg["id"]] = msg
                    self.cond.notify_all()
        with self.cond:
            self.cond.notify_all()

    def send(self, message: dict) -> None:
        try:
            self.proc.stdin.write(json.dumps(message) + "\n")
            self.proc.stdin.flush()
        except (OSError, ValueError) as exc:
            raise McpError(f"il server si è chiuso: {self.last_error()}") from exc

    def request(self, message: dict, timeout: float) -> dict:
        self.send(message)
        with self.cond:
            done = self.cond.wait_for(lambda: message["id"] in self.pending or self.proc.poll() is not None,
                                      timeout)
            if message["id"] in self.pending:
                return self.pending.pop(message["id"])
        raise McpError(f"nessuna risposta dopo {timeout:.0f}s" if not done else
                       f"il server si è chiuso: {self.last_error()}")

    def last_error(self) -> str:
        return " ".join(line.strip() for line in list(self.stderr)[-3:]) or f"exit {self.proc.poll()}"

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class HttpTransport:
    """Streamable HTTP: POST di JSON-RPC, risposta JSON oppure eventi SSE."""

    def __init__(self, url: str, headers: dict[str, str], client: httpx.Client | None = None) -> None:
        self.url = url
        self.headers = {"Accept": "application/json, text/event-stream", **headers}
        self.client = client or httpx.Client(timeout=TIMEOUT, follow_redirects=True)
        self.session_id = ""

    def send(self, message: dict) -> None:
        self._post(message)

    def request(self, message: dict, timeout: float) -> dict:
        response = self._post(message, timeout)
        if "text/event-stream" in response.headers.get("content-type", ""):
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    try:
                        msg = json.loads(line[5:])
                    except ValueError:
                        continue
                    if isinstance(msg, dict) and msg.get("id") == message["id"]:
                        return msg
            raise McpError("nessuna risposta nello stream SSE")
        return response.json()

    def _post(self, message: dict, timeout: float = TIMEOUT) -> httpx.Response:
        headers = {**self.headers, **({"Mcp-Session-Id": self.session_id} if self.session_id else {})}
        try:
            response = self.client.post(self.url, json=message, headers=headers, timeout=timeout)
        except httpx.HTTPError as exc:
            raise McpError(f"{type(exc).__name__}: {exc}") from exc
        if response.status_code == 401:
            raise McpError("serve l'autenticazione: aggiungi il token negli headers della configurazione")
        if response.status_code >= 400:
            raise McpError(f"HTTP {response.status_code}: {response.text[:200]}")
        self.session_id = response.headers.get("mcp-session-id", self.session_id)
        return response

    def close(self) -> None:
        self.client.close()


# -------------------------------------------------------------------- server
@dataclass
class Server:
    config: ServerConfig
    root: Path
    tools: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    instructions: str = ""

    def __post_init__(self) -> None:
        self.transport: StdioTransport | HttpTransport | None = None
        self.ids = itertools.count(1)
        self.lock = threading.Lock()

    @property
    def name(self) -> str:
        return self.config.name

    def connect(self) -> None:
        """Avvia (o contatta) il server e legge i suoi strumenti. Gli errori finiscono in `error`."""
        with self.lock:
            if self.transport or self.error:
                return
            try:
                self._connect()
            except (McpError, OSError, ValueError) as exc:
                self.error = str(exc) or type(exc).__name__
                self.close()

    def _connect(self) -> None:
        extra = {"CLAUDE_PROJECT_DIR": str(self.root)}
        if self.config.plugin_root:
            extra["CLAUDE_PLUGIN_ROOT"] = str(self.config.plugin_root)
        cfg = expand(self.config.config, extra)
        if self.config.kind == "stdio":
            if not cfg.get("command"):
                raise McpError("manca `command`")
            self.transport = StdioTransport([str(cfg["command"]), *map(str, cfg.get("args", []))],
                                            {k: str(v) for k, v in (cfg.get("env") or {}).items()}, self.root)
        elif self.config.kind == "http":
            self.transport = HttpTransport(str(cfg["url"]), {k: str(v) for k, v in (cfg.get("headers") or {}).items()})
        else:  # ponytail: il vecchio trasporto "sse" e l'OAuth non ci sono; li aggiungeremo se servono
            raise McpError(f"trasporto «{self.config.kind}» non ancora supportato (usa stdio o http)")
        info = self._call("initialize", {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                         "clientInfo": {"name": "mydevagent", "version": "1"}})
        self.instructions = str(info.get("instructions") or "")
        self.transport.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        tools, cursor = [], None
        while True:
            page = self._call("tools/list", {"cursor": cursor} if cursor else {})
            tools += [t for t in page.get("tools", []) if isinstance(t, dict) and t.get("name")]
            cursor = page.get("nextCursor")
            if not cursor:
                break
        self.tools = tools

    def _call(self, method: str, params: dict, timeout: float = TIMEOUT) -> dict:
        if not self.transport:
            raise McpError(self.error or "non connesso")
        reply = self.transport.request({"jsonrpc": "2.0", "id": next(self.ids), "method": method,
                                        "params": params}, timeout)
        if "error" in reply:
            err = reply["error"]
            raise McpError(str(err.get("message", err)) if isinstance(err, dict) else str(err))
        return reply.get("result") or {}

    def tool(self, name: str) -> dict | None:
        return next((t for t in self.tools if t["name"] == name), None)

    def call(self, name: str, arguments: dict[str, Any]) -> str:
        result = self._call("tools/call", {"name": name, "arguments": arguments},
                            timeout=float(self.config.config.get("timeout") or 300))
        parts = []
        for item in result.get("content", []):
            kind = item.get("type")
            if kind == "text":
                parts.append(str(item.get("text", "")))
            elif kind == "resource":
                resource = item.get("resource") or {}
                parts.append(str(resource.get("text") or f"[risorsa {resource.get('uri', '')}]"))
            else:
                parts.append(f"[{kind}]")
        if not parts and result.get("structuredContent") is not None:
            parts.append(json.dumps(result["structuredContent"], ensure_ascii=False))
        text = "\n".join(parts) or "(nessun risultato)"
        return f"ERROR: {text}" if result.get("isError") else text

    def close(self) -> None:
        if self.transport:
            self.transport.close()
        self.transport = None


class McpManager:
    """I server del progetto: si avviano alla prima richiesta (o in background all'avvio della TUI)."""

    def __init__(self, root: Path, configs: dict[str, ServerConfig] | None = None) -> None:
        self.root = Path(root).resolve()
        if configs is None:
            pending = {c.name for c in untrusted(self.root)}
            configs = {k: v for k, v in server_configs(self.root).items() if k not in pending}
        self.servers = {name: Server(config, self.root) for name, config in configs.items()
                        if not config.config.get("disabled")}

    def __bool__(self) -> bool:
        return bool(self.servers)

    def connect_all(self) -> None:
        threads = [threading.Thread(target=s.connect, daemon=True) for s in self.servers.values()]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    def prompt(self) -> str:
        """L'elenco per il system prompt: server e nomi degli strumenti (gli argomenti si chiedono col tool)."""
        if not self.servers:
            return ""
        lines = []
        for server in self.servers.values():
            if server.error:
                continue
            names = ", ".join(t["name"] for t in server.tools[:40]) if server.tools else "(tools not loaded yet)"
            lines.append(f"- {server.name}: {names}")
        if not lines:
            return ""
        return ("# MCP servers\nExternal tools. Call the `mcp` tool with `server` only to see a server's tools "
                "and their arguments, then with `server`, `tool` and `arguments` to use one.\n" + "\n".join(lines))

    def list_tools(self, server: Server) -> str:
        lines = [f"Tools of MCP server '{server.name}':"]
        for tool in server.tools:
            schema = tool.get("inputSchema") or {}
            props = schema.get("properties") or {}
            required = set(schema.get("required") or [])
            args = ", ".join(f"{k}{'' if k in required else '?'}: {v.get('type', 'any')}"
                             + (f" ({str(v.get('description'))[:80]})" if v.get("description") else "")
                             for k, v in props.items())
            lines.append(f"- {tool['name']}({args}): {str(tool.get('description') or '')[:200]}")
        return "\n".join(lines)

    def close(self) -> None:
        for server in self.servers.values():
            server.close()
