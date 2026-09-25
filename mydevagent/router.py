"""Router: decide modalità (fast/balanced/deep) e quali dei 15 agenti attivare.

Euristiche deterministiche (0 token, <1 ms) con fallback opzionale a un modello piccolo.
Override dell'utente: `/fast`, `/balanced`, `/deep`, `@security`, `@perf`, `@web`, ...
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .config import Settings
from .registry import AgentRegistry

MODE_CMD_RE = re.compile(r"(?<![\w/])/(fast|balanced|deep)\b", re.IGNORECASE)
MENTION_RE = re.compile(r"(?<![\w@])@([a-zA-Z_][\w-]*)")
FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
URL_RE = re.compile(r"https?://\S+")
TRACE_LINE_RE = re.compile(r"^\s*(File \".*\", line \d+|at .+\(.+:\d+:\d+\)|Traceback|\S+Error:|\S+Exception)", re.M)
DEEP_HINTS = (
    "production-ready", "production ready", "pronto per la produzione", "in produzione", "enterprise",
    "end-to-end", "end to end", "full-stack", "full stack", "app completa", "applicazione completa",
    "sistema completo", "complete app", "from scratch", "da zero", "saas", "mvp completo",
)
MAX_SPECIALISTS = 4


@dataclass
class Route:
    mode: str
    primary: str
    specialists: list[str] = field(default_factory=list)
    gate: list[str] = field(default_factory=list)
    research: bool = False
    docs: bool = False
    request: str = ""
    reasons: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)

    @property
    def agents(self) -> list[str]:
        """Agenti coinvolti, nell'ordine in cui lavorano."""
        if self.mode == "fast":
            return [self.primary, "formatter"]
        order = (["research"] if self.research else []) + ["architect"] + self.specialists + ["debug_test"]
        order += self.gate + (["docs"] if self.docs else []) + ["formatter"]
        return list(dict.fromkeys(order))


def prose_length(text: str) -> int:
    """Lunghezza della parte "discorsiva": codice incollato e traceback non contano."""
    text = FENCE_RE.sub(" ", text)
    text = TRACE_LINE_RE.sub(" ", text)
    return len(" ".join(text.split()))


class Router:
    def __init__(self, settings: Settings, registry: AgentRegistry, llm=None) -> None:
        self.settings = settings
        self.registry = registry
        self.llm = llm
        self._patterns = {
            agent.key: [self._compile(k) for k in agent.keywords] for agent in registry
        }

    @staticmethod
    def _compile(keyword: str) -> re.Pattern[str]:
        stripped = keyword.strip()
        if re.fullmatch(r"[\w .\-/']+", stripped) and stripped[:1].isalnum() and stripped[-1:].isalnum():
            return re.compile(rf"(?<![\w]){re.escape(stripped)}(?![\w])", re.IGNORECASE)
        return re.compile(re.escape(keyword), re.IGNORECASE)

    def score(self, text: str) -> dict[str, int]:
        padded = f" {text} "
        scores = {}
        for key, patterns in self._patterns.items():
            hits = sum(1 for p in patterns if p.search(padded))
            if hits:
                scores[key] = hits
        return scores

    def route(self, request: str, *, mode: str | None = None, has_images: bool = False) -> Route:
        reasons: list[str] = []
        forced = None
        match = MODE_CMD_RE.search(request)
        if match:
            forced = match.group(1).lower()
            reasons.append(f"mode forced by /{forced}")
        text = MODE_CMD_RE.sub(" ", request)

        mentions: list[str] = []

        def _strip_mentions(segment: str) -> str:
            def repl(m: re.Match[str]) -> str:
                key = self.registry.resolve(m.group(1))
                if key is None:
                    return m.group(0)
                mentions.append(key)
                return " "

            return MENTION_RE.sub(repl, segment)

        # le menzioni valgono solo fuori dai blocchi di codice (es. @Test in Java resta intatto)
        parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
        clean = "".join(p if p.startswith("```") else _strip_mentions(p) for p in parts).strip()
        if mentions:
            reasons.append("mentions: " + ", ".join("@" + m for m in dict.fromkeys(mentions)))

        scores = self.score(FENCE_RE.sub(" ", clean))
        for key in mentions:
            scores[key] = scores.get(key, 0) + 100
        scores.pop("formatter", None)

        stage = {a.key: a.stage for a in self.registry}
        research = "research" in scores or bool(URL_RE.search(clean))
        if has_images and "frontend" not in scores and re.search(r"\b(ui|mockup|design|layout|pagina|page)\b",
                                                                 clean, re.I):
            scores["frontend"] = 1

        domain_keys = [k for k in scores if stage[k] in ("specialist", "test", "gate", "docs", "plan")]
        n_domains = len({k for k in domain_keys if stage[k] == "specialist"}) + (1 if "debug_test" in scores else 0)

        mode = forced or (mode if mode and mode != "auto" else None)
        if mode is None and self.settings.router.default_mode != "auto":
            mode = self.settings.router.default_mode
        if mode is None:
            rcfg = self.settings.router
            length = prose_length(clean)
            if any(h in clean.lower() for h in DEEP_HINTS):
                mode, why = "deep", "complex/production request"
            elif length >= rcfg.deep_min_chars or n_domains >= rcfg.deep_min_domains:
                mode, why = "deep", f"{n_domains} domains, {length} chars"
            elif length <= rcfg.fast_max_chars and len(domain_keys) <= 1:
                mode, why = "fast", f"short ({length} chars), single domain"
            else:
                mode, why = "balanced", f"{len(domain_keys)} domains, {length} chars"
            if self.settings.router.use_llm and self.llm is not None and not domain_keys:
                llm_route = self._llm_route(clean)
                if llm_route:
                    mode = llm_route.get("mode", mode)
                    for key in llm_route.get("agents", []):
                        if key in stage and key != "formatter":
                            scores.setdefault(key, 1)
                    why += " + LLM router"
            reasons.append(why)
        if mode not in ("fast", "balanced", "deep"):
            mode = "balanced"

        ranked = sorted(scores, key=lambda k: (-scores[k], self.registry[k].id))
        eligible_primary = [k for k in ranked if k not in ("research", "formatter")]
        primary = eligible_primary[0] if eligible_primary else "language"

        specialists = [k for k in ranked if stage[k] == "specialist"][:MAX_SPECIALISTS]
        if not specialists:
            specialists = ["language"]
        mode_cfg = self.settings.mode(mode)
        gate = list(mode_cfg.gate)
        for key in ranked:
            if stage[key] == "gate" and key not in gate:
                gate.append(key)
        gate = [g for g in gate if g in stage]
        docs = mode_cfg.docs or "docs" in scores

        return Route(
            mode=mode,
            primary=primary,
            specialists=specialists,
            gate=gate,
            research=research,
            docs=docs,
            request=clean,
            reasons=reasons,
            scores=scores,
        )

    def _llm_route(self, text: str) -> dict | None:
        keys = ", ".join(a.key for a in self.registry if a.key != "formatter")
        prompt = (
            "Classify this programming request. Reply with JSON only: "
            '{"mode": "fast|balanced|deep", "agents": [keys]} using keys from: ' + keys +
            ". fast = one simple answer; deep = large/production system.\nRequest: " + text[:1500]
        )
        try:
            out = self.llm.complete([{"role": "user", "content": prompt}], tier="fast", max_tokens=80,
                                    temperature=0.0).text
            match = re.search(r"\{.*\}", out, re.DOTALL)
            return json.loads(match.group(0)) if match else None
        except Exception:
            return None
