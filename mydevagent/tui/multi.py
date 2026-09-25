"""Multigiocatore: gli amici sulla tua rete (stesso Wi-Fi) aprono un link e seguono la sessione dal browser:
vedono il lavoro dell'agente com'è nel tuo terminale e gli scrivono. I loro messaggi arrivano nella tua UI
e l'agente li esegue come i tuoi, ma modifiche e comandi li confermi sempre tu. Serve il codice di /multi.

    GET  /                 la pagina per gli amici
    GET  /events?codice=   il feed della sessione (Server-Sent Events, riprende da Last-Event-ID)
    POST /join  /send      {codice, nome[, testo]}
"""

from __future__ import annotations

import contextlib
import html
import io
import json
import queue
import re
import secrets
import socket
import threading
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from rich.console import Console
from rich.segment import Segment
from rich.terminal_theme import MONOKAI, TerminalTheme

PAGE = Path(__file__).with_name("multi.html")
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # niente 0/O e 1/I: si detta a voce
DEFAULT_PORT = 8765
WIDTH = 90  # colonne del «terminale» nella pagina
MAX_TEXT = 4000
MAX_FEED = 5000
MAX_FAILURES = 20  # codici sbagliati per indirizzo, poi basta
KEEPALIVE_S = 15
# i colori di Monokai sullo sfondo della pagina
THEME = TerminalTheme((21, 17, 27), (217, 217, 217), [MONOKAI.ansi_colors[i] for i in range(8)],
                      [MONOKAI.ansi_colors[i] for i in range(8, 16)])


def lan_ip() -> str:
    """L'indirizzo di questo PC nella rete locale (non parte nessun pacchetto: serve solo a scegliere la scheda)."""
    with contextlib.suppress(OSError), socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    return "127.0.0.1"


def clean_name(name: Any) -> str:
    name = re.sub(r"[^\w .'()-]", "", str(name or ""))[:20].strip()
    return name or "Ospite"


class _Nowhere(io.StringIO):
    def write(self, s: str) -> int:
        return len(s)


class Tee:
    """Stampa sulla console dell'host e su quella della stanza."""

    def __init__(self, *consoles: Console) -> None:
        self.consoles = consoles

    def print(self, *args, **kwargs) -> None:
        for console in self.consoles:
            console.print(*args, **kwargs)


def to_html(console: Console) -> str:
    """Quello che la console (record=True) ha registrato, in HTML, e svuota la registrazione.

    Niente link: export_html di Rich li scrive senza escape, e nelle risposte del modello può esserci di tutto.
    """
    with console._record_buffer_lock:
        segments = list(Segment.filter_control(Segment.simplify(console._record_buffer)))
        del console._record_buffer[:]
    out = []
    for text, style, _ in segments:
        rule = style.get_html_style(THEME) if style else ""
        out.append(f'<span style="{rule}">{html.escape(text)}</span>' if rule else html.escape(text))
    return "".join(out)


class Room:
    """La stanza: il feed di quello che succede, chi si è collegato e i messaggi degli amici per l'host."""

    def __init__(self, host: str, port: int = DEFAULT_PORT, bind: str = "0.0.0.0") -> None:
        self.host = host
        self.code = "".join(secrets.choice(ALPHABET) for _ in range(6))
        self.console = Console(file=_Nowhere(), record=True, width=WIDTH, force_terminal=True,
                               color_system="truecolor")  # quello che stampi qui finisce nella pagina
        self.feed: list[dict[str, Any]] = []
        self.next_id = 0
        self.guests: list[str] = []
        self.inbox: queue.Queue[tuple[str, str]] = queue.Queue()
        self.on_message: Callable[[], None] = lambda: None
        self.on_join: Callable[[str], None] = lambda name: None
        self.failures: dict[str, int] = {}
        self.closed = False
        self._cond = threading.Condition()
        self.page = PAGE.read_bytes()
        try:
            self.server = ThreadingHTTPServer((bind, port), _Handler)
        except OSError:  # porta occupata: una libera qualsiasi
            self.server = ThreadingHTTPServer((bind, 0), _Handler)
        self.server.daemon_threads = True
        self.server.room = self
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def link(self) -> str:
        return f"http://{lan_ip()}:{self.port}/?codice={self.code}"

    # ------------------------------------------------------------------ feed
    def publish(self, item: dict[str, Any]) -> None:
        with self._cond:
            self.feed.append({**item, "id": self.next_id})
            self.next_id += 1
            del self.feed[:-MAX_FEED]
            self._cond.notify_all()

    def flush(self) -> None:
        """Manda agli amici quello che è stato stampato su self.console."""
        chunk = to_html(self.console)
        if chunk:
            self.publish({"kind": "html", "html": chunk})

    def system(self, text: str) -> None:
        self.publish({"kind": "system", "text": text})

    def items_after(self, since: int, timeout: float) -> list[dict[str, Any]]:
        with self._cond:
            if not self.closed and not (self.feed and self.feed[-1]["id"] > since):
                self._cond.wait(timeout)
            return [i for i in self.feed if i["id"] > since]

    # --------------------------------------------------------------- amici
    def allowed(self, address: str, code: Any) -> bool:
        if self.failures.get(address, 0) >= MAX_FAILURES:
            return False
        if secrets.compare_digest(str(code or "").strip().upper(), self.code):
            return True
        self.failures[address] = self.failures.get(address, 0) + 1
        return False

    def join(self, name: Any) -> str:
        name = clean_name(name)
        if name.lower() == self.host.lower():
            name += " (ospite)"
        if name not in self.guests:
            self.guests.append(name)
            self.system(f"{name} si è collegato")
            self.on_join(name)
        return name

    def message(self, name: str, text: str) -> None:
        self.publish({"kind": "message", "who": name, "text": text})
        self.inbox.put((name, text))
        self.on_message()

    def next_message(self) -> tuple[str, str] | None:
        try:
            return self.inbox.get_nowait()
        except queue.Empty:
            return None

    def close(self) -> None:
        with self._cond:
            self.closed = True
            self._cond.notify_all()
        self.server.shutdown()
        self.server.server_close()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    @property
    def room(self) -> Room:
        return self.server.room  # type: ignore[attr-defined]

    def _reply(self, code: int, body: bytes, kind: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", f"{kind}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _refuse(self) -> None:
        tired = self.room.failures.get(self.client_address[0], 0) >= MAX_FAILURES
        self._reply(429 if tired else 403, b'{"error": "codice sbagliato"}')

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/":
            self._reply(200, self.room.page, "text/html")
        elif url.path == "/events":
            if not self.room.allowed(self.client_address[0], parse_qs(url.query).get("codice", [""])[0]):
                self._refuse()
                return
            try:
                since = int(self.headers.get("Last-Event-ID") or -1)
            except ValueError:
                since = -1
            self._events(since)
        else:
            self._reply(404, b'{"error": "non trovato"}')

    def _events(self, since: int) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while True:
                items = self.room.items_after(since, KEEPALIVE_S)
                for item in items:
                    self.wfile.write(f"id: {item['id']}\ndata: {json.dumps(item)}\n\n".encode())
                    since = item["id"]
                if not items:
                    self.wfile.write(b": ping\n\n")  # tiene viva la connessione
                self.wfile.flush()
                if self.room.closed:
                    break
        except OSError:
            pass  # l'amico ha chiuso la pagina

    def do_POST(self) -> None:
        try:
            size = min(int(self.headers.get("Content-Length") or 0), MAX_TEXT * 4)
            data = json.loads(self.rfile.read(size) or b"{}")
        except (ValueError, OSError):
            self._reply(400, b'{"error": "richiesta non valida"}')
            return
        if not isinstance(data, dict) or not self.room.allowed(self.client_address[0], data.get("codice")):
            self._refuse()
            return
        path = urlparse(self.path).path
        if path not in ("/join", "/send"):
            self._reply(404, b'{"error": "non trovato"}')
            return
        name = self.room.join(data.get("nome"))
        text = str(data.get("testo") or "").strip()[:MAX_TEXT]
        if path == "/send" and text:
            self.room.message(name, text)
        self._reply(200, json.dumps({"host": self.room.host, "nome": name}).encode())
