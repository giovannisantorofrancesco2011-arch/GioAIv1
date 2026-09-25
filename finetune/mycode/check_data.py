#!/usr/bin/env python3
"""Controlla i file .jsonl di MyCode prima dell'addestramento.

  python finetune/mycode/check_data.py                      # tutti i file in finetune/mycode/data
  python finetune/mycode/check_data.py mio.jsonl altro.jsonl

Ogni riga è {"messages": [...], "source": "..."}: prima il messaggio di sistema (SYSTEM.txt, oppure
AGENT_SYSTEM.txt per gli esempi in modalità agente), poi utente e assistente alternati, e l'ultima parola è
dell'assistente. Negli esempi agente le chiamate ai tool usano il formato testuale di MyDevAgent
`<tool name="...">{json}</tool>` e i risultati tornano come `<result name="...">…</result>`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = {"read_file", "list_files", "grep", "edit_file", "write_file", "bash", "run_tests", "todo_write"}
TOOL_RE = re.compile(r"<tool\s+name=\"([\w.-]+)\">(.*?)</tool>", re.DOTALL)
RESULT_RE = re.compile(r"<result name=\"([\w.-]+)\">\n.*?\n</result>", re.DOTALL)
MAX_CHARS = 6500  # ~2048 token: il contesto usato per l'addestramento sulla RTX 4060


def check_row(row: dict, system: str, agent_system: str) -> tuple[str, list[str]]:
    """→ (tipo, errori). tipo è "chat" o "agent"."""
    errors: list[str] = []
    msgs = row.get("messages")
    if not isinstance(msgs, list) or len(msgs) < 3:
        return "?", ["servono almeno sistema, utente e assistente"]
    if not isinstance(row.get("source"), str):
        errors.append("manca source")
    first = msgs[0]
    kind = "agent" if first.get("content", "").strip() == agent_system else "chat"
    if first.get("role") != "system" or first.get("content", "").strip() not in (system, agent_system):
        errors.append("il primo messaggio deve essere SYSTEM.txt o AGENT_SYSTEM.txt")
    for i, msg in enumerate(msgs[1:]):
        want = "user" if i % 2 == 0 else "assistant"
        if msg.get("role") != want:
            errors.append(f"messaggio {i + 1}: ruolo {msg.get('role')!r}, atteso {want!r}")
        if not isinstance(msg.get("content"), str) or not msg["content"].strip():
            errors.append(f"messaggio {i + 1}: vuoto")
    if msgs[-1].get("role") != "assistant":
        errors.append("l'ultimo messaggio deve essere dell'assistente")
    if sum(len(str(m.get("content", ""))) for m in msgs) > MAX_CHARS:
        errors.append(f"troppo lungo (> {MAX_CHARS} caratteri)")
    if errors:
        return kind, errors

    pending: list[str] = []
    for i, msg in enumerate(msgs[1:], 1):
        text = msg["content"]
        if msg["role"] == "assistant":
            calls = TOOL_RE.findall(text)
            if kind == "chat" and "<tool" in text:
                errors.append(f"messaggio {i}: chiamata a un tool in un esempio senza tool")
            for name, raw in calls:
                if name not in TOOLS:
                    errors.append(f"messaggio {i}: tool sconosciuto {name}")
                try:
                    if not isinstance(json.loads(raw, strict=False), dict):
                        raise ValueError
                except ValueError:
                    errors.append(f"messaggio {i}: argomenti JSON non validi per {name}")
            if text.count("<tool") != len(calls):
                errors.append(f"messaggio {i}: chiamata a un tool scritta male")
            pending = [name for name, _ in calls]
        else:
            results = RESULT_RE.findall(text)
            if pending and results != pending:
                errors.append(f"messaggio {i}: risultati {results} per le chiamate {pending}")
            if not pending and text.lstrip().startswith("<result"):
                errors.append(f"messaggio {i}: risultato senza chiamata")
            pending = []
    if kind == "agent" and TOOL_RE.search(msgs[-1]["content"]):
        errors.append("la risposta finale non deve chiamare tool")
    return kind, errors


def main() -> None:
    files = [Path(p) for p in sys.argv[1:]] or sorted((HERE / "data").glob("*.jsonl"))
    system = (HERE / "SYSTEM.txt").read_text(encoding="utf-8").strip()
    agent_system = (HERE / "AGENT_SYSTEM.txt").read_text(encoding="utf-8").strip()
    total, bad, kinds, seen = 0, 0, {"chat": 0, "agent": 0}, set()
    for path in files:
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            total += 1
            try:
                row = json.loads(line)
                kind, errors = check_row(row, system, agent_system)
                first_user = row["messages"][1]["content"].strip().lower()
                if first_user in seen:
                    errors.append("domanda duplicata")
                seen.add(first_user)
            except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
                kind, errors = "?", [f"riga non valida: {exc}"]
            if errors:
                bad += 1
                print(f"{path.name}:{n}: " + "; ".join(errors))
            elif kind in kinds:
                kinds[kind] += 1
    print(f"{total} esempi: {kinds['chat']} chat, {kinds['agent']} agente, {bad} con errori")
    sys.exit(1 if bad or not total else 0)


if __name__ == "__main__":
    main()
