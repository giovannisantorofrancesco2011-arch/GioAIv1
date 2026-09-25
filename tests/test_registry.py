from mydevagent.registry import EXPECTED_AGENT_COUNT, SECTIONS
from mydevagent.tools import Toolbox


def test_exactly_15_agents(registry):
    assert len(registry) == EXPECTED_AGENT_COUNT == 15
    assert [a.id for a in registry] == list(range(1, 16))


def test_every_agent_has_prompt_and_valid_reads(registry):
    for agent in registry:
        assert agent.prompt.startswith("# Role:"), agent.key
        assert set(agent.reads) <= set(SECTIONS)


def test_agent_tools_exist(settings, registry):
    available = Toolbox(settings).available()
    for agent in registry:
        for name in agent.tools:
            assert name in available, f"{agent.key} uses unknown tool {name}"


def test_aliases_resolve(registry):
    assert registry.resolve("@sec") == "security"
    assert registry.resolve("perf") == "performance"
    assert registry.resolve("web") == "research"
    assert registry.resolve("nope") is None


def test_every_tier_resolves(settings):
    for profile in settings.profiles:
        settings.profile = profile
        for tier in ("main", "fast", "reasoning", "vision", "embed"):
            model, backend = settings.resolve_model(tier)
            assert model and backend.base_url.startswith("http")
