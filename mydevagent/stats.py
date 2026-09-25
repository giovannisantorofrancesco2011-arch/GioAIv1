"""Statistiche d'uso per /stats: ogni richiesta aggiunge una riga a ~/.mydevagent/stats.jsonl.

Si contano gli stessi eventi che disegnano la UI (token, tool, diff, test), sia dal terminale sia da
MyDevAgent Studio. Il file è in JSON Lines: più finestre possono scriverci insieme, una riga rotta si salta.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any


def stats_file() -> Path:
    return Path(os.environ.get("MYDEVAGENT_STATE_DIR", Path.home() / ".mydevagent")) / "stats.jsonl"


@dataclass
class Turn:
    """Una richiesta: si riempie con gli eventi del turno, poi `finish()` la chiude e la salva."""

    project: str = ""
    session: str = ""
    source: str = "terminale"  # terminale | studio
    model: str = ""
    team: str = ""
    started: float = field(default_factory=time.time)
    seconds: float = 0.0
    tokens: int = 0
    tools: int = 0
    files: list[str] = field(default_factory=list)
    added: int = 0
    removed: int = 0
    tests_ok: int = 0
    tests_failed: int = 0
    cancelled: bool = False
    failed: bool = False

    def on_event(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "route":
            self.team = event.get("mode", "")
        elif kind == "llm_call" or (kind == "agent_end" and not event.get("counted") and event.get("agent") != "final"):
            # gli agent_end «counted» riassumono chiamate già arrivate come llm_call
            self.tokens += event.get("prompt_tokens", 0) + event.get("completion_tokens", 0)
        elif kind == "tool_result":
            self.tools += 1
        elif kind == "diff":
            if event.get("path") and event["path"] not in self.files:
                self.files.append(event["path"])
            self.added += event.get("added", 0)
            self.removed += event.get("removed", 0)
        elif kind == "tests":
            if event.get("ok"):
                self.tests_ok += 1
            else:
                self.tests_failed += 1
        elif kind == "cancelled":
            self.cancelled = True

    def finish(self, answer: str = "", *, estimate: bool = False, failed: bool = False, save: bool = True
               ) -> dict[str, Any]:
        """`estimate`: la risposta finale arriva in streaming senza conteggio, la stima come la UI (caratteri/4)."""
        self.seconds = round(time.time() - self.started, 1)
        if estimate:
            self.tokens += len(answer) // 4
        self.failed = self.failed or failed
        record = asdict(self)
        if save:
            append(record)
        return record


def append(record: dict[str, Any]) -> None:
    """Aggiunge la riga al file. Le statistiche non devono mai far fallire un turno."""
    path = stats_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def day_of(record: dict[str, Any]) -> date:
    return date.fromtimestamp(float(record.get("started", 0)))


def load(days: int | None = None, today: date | None = None) -> list[dict[str, Any]]:
    """Le richieste salvate; con `days` solo quelle degli ultimi N giorni (oggi compreso)."""
    path = stats_file()
    if not path.is_file():
        return []
    first = (today or date.today()) - timedelta(days=days - 1) if days else None
    out = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and "started" in record and (first is None or day_of(record) >= first):
            out.append(record)
    return out


@dataclass
class Summary:
    turns: int = 0
    sessions: int = 0
    tokens: int = 0
    seconds: float = 0.0
    tools: int = 0
    files: int = 0
    added: int = 0
    removed: int = 0
    tests_ok: int = 0
    tests_failed: int = 0
    per_day: Counter = field(default_factory=Counter)  # date → richieste
    models: Counter = field(default_factory=Counter)
    teams: Counter = field(default_factory=Counter)
    projects: Counter = field(default_factory=Counter)
    hours: Counter = field(default_factory=Counter)

    def streaks(self, today: date | None = None) -> tuple[int, int]:
        """(serie attuale, serie più lunga) di giorni di fila. La serie attuale regge finché oggi non è finito."""
        days = set(self.per_day)
        longest = run = 0
        previous: date | None = None
        for day in sorted(days):
            run = run + 1 if previous and day - previous == timedelta(days=1) else 1
            longest = max(longest, run)
            previous = day
        today = today or date.today()
        current, day = 0, today if today in days else today - timedelta(days=1)
        while day in days:
            current += 1
            day -= timedelta(days=1)
        return current, longest

    def to_dict(self, today: date | None = None) -> dict[str, Any]:
        """Per MyDevAgent Studio (JSON)."""
        current, longest = self.streaks(today)
        top = {name: dict(counter.most_common(5)) for name, counter in
               (("models", self.models), ("teams", self.teams), ("projects", self.projects))}
        return {"turns": self.turns, "sessions": self.sessions, "tokens": self.tokens, "seconds": self.seconds,
                "tools": self.tools, "files": self.files, "added": self.added, "removed": self.removed,
                "tests_ok": self.tests_ok, "tests_failed": self.tests_failed, "streak": current, "longest": longest,
                "per_day": {d.isoformat(): n for d, n in sorted(self.per_day.items())}, **top}


def summarize(records: list[dict[str, Any]]) -> Summary:
    out = Summary()
    files: set[tuple[str, str]] = set()
    sessions: set[str] = set()
    for r in records:
        out.turns += 1
        out.tokens += int(r.get("tokens", 0))
        out.seconds += float(r.get("seconds", 0))
        out.tools += int(r.get("tools", 0))
        out.added += int(r.get("added", 0))
        out.removed += int(r.get("removed", 0))
        out.tests_ok += int(r.get("tests_ok", 0))
        out.tests_failed += int(r.get("tests_failed", 0))
        files.update((r.get("project", ""), f) for f in r.get("files", []))
        if r.get("session"):
            sessions.add(r["session"])
        out.per_day[day_of(r)] += 1
        out.hours[time.localtime(float(r["started"])).tm_hour] += 1
        for counter, key in ((out.models, "model"), (out.teams, "team"), (out.projects, "project")):
            if r.get(key):
                counter[r[key]] += 1
    out.files = len(files)
    out.sessions = len(sessions)
    return out
