"""Checkpoint dei file prima di ogni modifica → /undo e /rewind anche senza git."""

from __future__ import annotations

import difflib
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Checkpoint:
    id: int
    label: str
    created: float
    files: dict[str, bool]  # percorso relativo → esisteva prima della modifica?


class CheckpointStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.base = self.root / ".mydevagent" / "checkpoints"
        self.current: Checkpoint | None = None

    # ---------------------------------------------------------------- turni
    def begin(self, label: str) -> Checkpoint:
        ids = [c.id for c in self.list()]
        self.current = Checkpoint(id=(max(ids) + 1 if ids else 1), label=label[:80], created=time.time(), files={})
        return self.current

    def _dir(self, cp_id: int) -> Path:
        return self.base / f"{cp_id:04d}"

    def before_write(self, rel_path: str) -> None:
        """Salva lo stato originale del file (una volta per turno) prima di modificarlo."""
        if self.current is None:
            self.begin("modifica")
        cp = self.current
        if rel_path in cp.files:
            return
        source = self.root / rel_path
        existed = source.is_file()
        folder = self._dir(cp.id)
        if existed:
            target = folder / "files" / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        cp.files[rel_path] = existed
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "manifest.json").write_text(json.dumps(
            {"id": cp.id, "label": cp.label, "created": cp.created, "files": cp.files}, indent=1), encoding="utf-8")

    # --------------------------------------------------------------- lettura
    def list(self) -> list[Checkpoint]:
        if not self.base.is_dir():
            return []
        out = []
        for manifest in sorted(self.base.glob("*/manifest.json")):
            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                out.append(Checkpoint(data["id"], data["label"], data["created"], data["files"]))
            except (ValueError, KeyError, OSError):
                continue
        return sorted(out, key=lambda c: c.id)

    # -------------------------------------------------------------- ripristino
    def restore(self, cp: Checkpoint) -> list[str]:
        restored = []
        for rel, existed in cp.files.items():
            target = self.root / rel
            if existed:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(self._dir(cp.id) / "files" / rel, target)
            elif target.exists():
                target.unlink()
            restored.append(rel)
        shutil.rmtree(self._dir(cp.id), ignore_errors=True)
        if self.current and self.current.id == cp.id:
            self.current = None
        return restored

    def undo(self) -> tuple[Checkpoint, list[str]] | None:
        checkpoints = self.list()
        if not checkpoints:
            return None
        cp = checkpoints[-1]
        return cp, self.restore(cp)

    def rewind(self, cp_id: int) -> list[str]:
        """Annulla tutti i checkpoint dal più recente fino a `cp_id` compreso."""
        restored: list[str] = []
        for cp in reversed(self.list()):
            if cp.id < cp_id:
                break
            restored += self.restore(cp)
        return sorted(set(restored))

    def session_diff(self, since_id: int = 0) -> str:
        """Diff cumulativo delle modifiche dei checkpoint con id >= since_id rispetto a oggi."""
        originals: dict[str, str | None] = {}
        for cp in self.list():
            if cp.id < since_id:
                continue
            for rel, existed in cp.files.items():
                if rel in originals:
                    continue
                path = self._dir(cp.id) / "files" / rel
                originals[rel] = path.read_text(encoding="utf-8", errors="replace") if existed else None
        chunks = []
        for rel, old in sorted(originals.items()):
            current = self.root / rel
            new = current.read_text(encoding="utf-8", errors="replace") if current.is_file() else ""
            chunks.append("".join(difflib.unified_diff((old or "").splitlines(True), new.splitlines(True),
                                                       f"a/{rel}" if old is not None else "/dev/null",
                                                       f"b/{rel}")))
        return "".join(chunks)
