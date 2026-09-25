"""Skill: istruzioni riutilizzabili in cartelle, caricate solo quando servono (come le skill di Claude Code).

Una skill è una cartella con un `SKILL.md` (più eventuali file di supporto: esempi, script, modelli) oppure
un singolo file `<nome>.md`. In testa al file, opzionale:

    ---
    name: release-notes
    description: Scrive le note di rilascio dal git log. Usala quando l'utente chiede un changelog.
    ---

All'agente arriva solo l'elenco nome + descrizione; il contenuto lo legge con il tool `skill` quando una
richiesta corrisponde. Cartelle lette, dalla più specifica: `.mydevagent/skills` e `.claude/skills` del
progetto, `~/.mydevagent/skills`, `~/.claude/skills`, più quelle in MYDEVAGENT_SKILLS_DIRS (separate da `;`
su Windows e `:` altrove), per esempio la cartella delle skill di un altro agente.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

SKILL_FILES = ("SKILL.md", "skill.md", "Skill.md")
MAX_SKILL_CHARS = 12_000
MAX_DESCRIPTION = 300
FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


@dataclass
class Skill:
    name: str
    description: str
    path: Path  # il SKILL.md (o il file .md singolo)
    source: str  # progetto · utente · cartella extra

    @property
    def folder(self) -> Path | None:
        return self.path.parent if self.path.name in SKILL_FILES else None

    def body(self) -> str:
        return _split(self.path.read_text(encoding="utf-8", errors="replace"))[1].strip()[:MAX_SKILL_CHARS]

    def files(self) -> list[str]:
        if not self.folder:
            return []
        return sorted(p.relative_to(self.folder).as_posix() for p in self.folder.rglob("*")
                      if p.is_file() and p != self.path and not p.name.startswith("."))[:50]

    def read(self, file: str | None = None) -> str:
        """Il contenuto della skill, oppure uno dei suoi file di supporto (solo dentro la sua cartella)."""
        if not file:
            extra = self.files()
            listing = ("\n\nSupporting files (read them with the skill tool and `file`):\n"
                       + "\n".join(f"- {f}" for f in extra)) if extra else ""
            return f"# Skill: {self.name}\n{self.body()}{listing}"
        if not self.folder:
            return f"ERROR: the skill '{self.name}' has no supporting files"
        target = (self.folder / file).resolve()
        if not target.is_relative_to(self.folder.resolve()) or not target.is_file():
            return f"ERROR: file not found in skill '{self.name}': {file}"
        return target.read_text(encoding="utf-8", errors="replace")[:MAX_SKILL_CHARS]


def _split(text: str) -> tuple[dict[str, str], str]:
    """Frontmatter semplice `chiave: valore` → (metadati, corpo)."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() and not key.startswith((" ", "\t")):
            meta[key.strip().lower()] = value.strip().strip("\"'")
    return meta, text[match.end():]


def _describe(body: str) -> str:
    for line in body.splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line
    return ""


def skill_dirs(root: Path) -> list[tuple[Path, str]]:
    home = Path.home()
    state = Path(os.environ.get("MYDEVAGENT_STATE_DIR", home / ".mydevagent"))
    dirs = [(root / ".mydevagent" / "skills", "progetto"), (root / ".claude" / "skills", "progetto"),
            (state / "skills", "utente"), (home / ".claude" / "skills", "utente")]
    for raw in os.environ.get("MYDEVAGENT_SKILLS_DIRS", "").split(os.pathsep):
        if raw.strip():
            dirs.append((Path(raw.strip()).expanduser(), "extra"))
    return dirs


def load_skills(root: Path) -> dict[str, Skill]:
    """nome → skill. A parità di nome vince la cartella più specifica (il progetto)."""
    found: dict[str, Skill] = {}
    for folder, source in skill_dirs(Path(root)):
        if not folder.is_dir():
            continue
        candidates = [next((d / f for f in SKILL_FILES if (d / f).is_file()), None)
                      for d in sorted(folder.iterdir()) if d.is_dir()]
        candidates += sorted(p for p in folder.glob("*.md") if p.name.lower() not in ("readme.md",))
        for path in candidates:
            if path is None:
                continue
            try:
                meta, body = _split(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            default = path.parent.name if path.name in SKILL_FILES else path.stem
            name = re.sub(r"[^\w-]+", "-", meta.get("name") or default).strip("-").lower()
            if name and name not in found:
                description = (meta.get("description") or _describe(body))[:MAX_DESCRIPTION]
                found[name] = Skill(name, description, path, source)
    return found


def skills_prompt(skills: dict[str, Skill]) -> str:
    if not skills:
        return ""
    lines = "\n".join(f"- {s.name}: {s.description}" for s in skills.values())
    return ("# Skills\nThese skills contain expert instructions. When the request matches a skill, FIRST call "
            "the `skill` tool with its name, then follow its instructions.\n" + lines)
