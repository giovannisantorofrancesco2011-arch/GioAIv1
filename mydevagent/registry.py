"""Registro dei 15 agenti: carica config/agents.yaml e i prompt associati."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import Settings

EXPECTED_AGENT_COUNT = 15
STAGES = ("research", "plan", "specialist", "test", "gate", "docs", "final")
SECTIONS = (
    "request",
    "history",
    "files",
    "rag",
    "research",
    "plan",
    "artifacts",
    "test_report",
    "issues",
    "image_notes",
)


@dataclass(frozen=True)
class Agent:
    id: int
    key: str
    name: str
    stage: str
    role: str
    goal: str
    prompt: str
    tier: str = "main"
    max_tokens: int = 1200
    temperature: float = 0.2
    reads: tuple[str, ...] = ("request",)
    tools: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()


@dataclass
class AgentRegistry:
    agents: dict[str, Agent]
    persona: str
    by_alias: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for agent in self.agents.values():
            self.by_alias[agent.key] = agent.key
            for alias in agent.aliases:
                self.by_alias[alias.lower()] = agent.key

    def __getitem__(self, key: str) -> Agent:
        return self.agents[key]

    def __iter__(self):
        return iter(sorted(self.agents.values(), key=lambda a: a.id))

    def __len__(self) -> int:
        return len(self.agents)

    def by_stage(self, stage: str) -> list[Agent]:
        return [a for a in self if a.stage == stage]

    def resolve(self, name: str) -> str | None:
        """Alias o chiave → chiave agente (None se sconosciuto)."""
        return self.by_alias.get(name.lower().lstrip("@"))


def load_registry(settings: Settings, *, strict: bool = True) -> AgentRegistry:
    agents_file = Path(settings.config_dir) / "agents.yaml"
    data = yaml.safe_load(agents_file.read_text(encoding="utf-8")) or {}
    prompts_dir = Path(settings.prompts_dir)
    persona = (prompts_dir / "system_persona.md").read_text(encoding="utf-8").strip()

    agents: dict[str, Agent] = {}
    for raw in data.get("agents", []):
        prompt_path = prompts_dir / "agents" / raw["prompt"]
        if not prompt_path.is_file():
            raise FileNotFoundError(f"Prompt mancante per l'agente {raw['key']}: {prompt_path}")
        agent = Agent(
            id=int(raw["id"]),
            key=raw["key"],
            name=raw["name"],
            stage=raw["stage"],
            role=raw["role"],
            goal=raw["goal"],
            prompt=prompt_path.read_text(encoding="utf-8").strip(),
            tier=raw.get("tier", "main"),
            max_tokens=int(raw.get("max_tokens", 1200)),
            temperature=float(raw.get("temperature", 0.2)),
            reads=tuple(raw.get("reads", ["request"])),
            tools=tuple(raw.get("tools", [])),
            keywords=tuple(str(k).lower() for k in raw.get("keywords", [])),
            aliases=tuple(str(a).lower() for a in raw.get("aliases", [])),
        )
        _validate(agent)
        if agent.key in agents:
            raise ValueError(f"Chiave agente duplicata: {agent.key}")
        agents[agent.key] = agent

    if strict:
        if len(agents) != EXPECTED_AGENT_COUNT:
            raise ValueError(f"MyDevAgent richiede esattamente {EXPECTED_AGENT_COUNT} agenti, trovati {len(agents)}")
        for stage in ("plan", "specialist", "test", "gate", "final"):
            if not any(a.stage == stage for a in agents.values()):
                raise ValueError(f"Nessun agente con stage '{stage}'")
        if sorted(a.id for a in agents.values()) != list(range(1, EXPECTED_AGENT_COUNT + 1)):
            raise ValueError("Gli id degli agenti devono essere 1..15 senza buchi")
    return AgentRegistry(agents=agents, persona=persona)


def _validate(agent: Agent) -> None:
    if agent.stage not in STAGES:
        raise ValueError(f"{agent.key}: stage '{agent.stage}' non valido ({STAGES})")
    unknown = set(agent.reads) - set(SECTIONS)
    if unknown:
        raise ValueError(f"{agent.key}: sezioni sconosciute in 'reads': {sorted(unknown)}")
