import pytest

from mydevagent.router import Router, prose_length


@pytest.fixture
def router(settings, registry):
    return Router(settings, registry)


def test_short_single_domain_is_fast(router):
    r = router.route("Come inverto una lista in Python?")
    assert r.mode == "fast"
    assert r.primary == "language"
    assert r.agents == ["language", "formatter"]


def test_multi_domain_is_balanced(router):
    r = router.route("Crea un endpoint FastAPI che salva utenti su Postgres con SQLAlchemy")
    assert r.mode == "balanced"
    assert {"backend", "database"} <= set(r.specialists)
    assert r.agents[0] == "architect" and r.agents[-1] == "formatter"
    assert "reviewer" in r.gate


def test_production_request_is_deep(router):
    r = router.route("Build a production-ready SaaS with React, FastAPI, Postgres and Docker")
    assert r.mode == "deep"
    assert {"security", "performance", "edge_cases", "reviewer"} <= set(r.gate)
    assert r.docs


def test_mode_command_and_mentions(router):
    r = router.route("/deep scrivi una funzione @sec @web")
    assert r.mode == "deep"
    assert r.research
    assert "security" in r.gate
    assert "@sec" not in r.request and "/deep" not in r.request


def test_mentions_inside_code_are_ignored(router):
    r = router.route("fix this\n```java\n@Test\nvoid t() {}\n```")
    assert "@Test" in r.request
    assert "debug_test" not in r.scores or r.scores["debug_test"] < 100


def test_pasted_traceback_does_not_force_deep(router):
    trace = "Traceback (most recent call last):\n" + '  File "a.py", line 3, in <module>\n' * 80
    r = router.route("Perché fallisce?\n```\n" + trace + "ValueError: x\n```")
    assert r.mode == "fast"
    assert r.primary == "debug_test"
    assert prose_length("```\n" + trace + "```") == 0


def test_ci_is_not_matched_in_italian_text(router):
    r = router.route("ci sono problemi con questa funzione python?")
    assert "devops" not in r.scores


def test_security_keyword_adds_gate_in_balanced(router):
    r = router.route("Crea un login sicuro con JWT in Express e una tabella users in MySQL")
    assert "security" in r.gate
