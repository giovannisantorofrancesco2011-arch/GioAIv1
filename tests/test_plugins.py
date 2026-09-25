import json
import subprocess

import pytest

from mydevagent import plugins
from mydevagent.skills import load_skills, skills_prompt
from mydevagent.tui.extras import custom_commands, expand_command


@pytest.fixture(autouse=True)
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("MYDEVAGENT_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.delenv("MYDEVAGENT_PLUGINS_DIRS", raising=False)
    return tmp_path / "home"


def make_plugin(folder, name="revisore"):
    """Un plugin come quelli di Claude Code: manifest, comandi (anche in sottocartelle), skill, agenti, hook."""
    (folder / ".claude-plugin").mkdir(parents=True)
    (folder / ".claude-plugin" / "plugin.json").write_text(json.dumps(
        {"name": name, "version": "1.2.0", "description": "Revisione del codice"}))
    (folder / "commands" / "git").mkdir(parents=True)
    (folder / "commands" / "git" / "rivedi.md").write_text(
        "---\ndescription: Rivede un file\nargument-hint: <file>\n---\n"
        "Rivedi $1 con ${CLAUDE_PLUGIN_ROOT}/checklist.md. Note: $ARGUMENTS\nStato: !`git status`\n")
    (folder / "skills" / "sicurezza").mkdir(parents=True)
    (folder / "skills" / "sicurezza" / "SKILL.md").write_text(
        "---\nname: sicurezza\ndescription: Cerca problemi di sicurezza.\n---\nControlla input e segreti.\n")
    (folder / "agents").mkdir()
    (folder / "agents" / "critico.md").write_text(
        "---\nname: critico\ndescription: Revisore severo. Examples: <example>lungo</example>\ntools: Read\n---\n"
        "Sei un revisore severo.\n")
    (folder / "hooks").mkdir()
    (folder / "hooks" / "hooks.json").write_text("{}")
    return folder


def test_load_plugins_from_every_source(tmp_path, home, monkeypatch):
    project = tmp_path / "progetto"
    make_plugin(project / ".mydevagent" / "plugins" / "revisore")
    # installati in Claude Code: formato v2 (lista), v1 (dizionario), uno disattivato
    cc = home / ".claude" / "plugins"
    for name in ("formatta", "vecchio", "spento"):
        (cc / "cache" / name / "commands").mkdir(parents=True)
    (cc / "installed_plugins.json").write_text(json.dumps({"version": 2, "plugins": {
        "formatta@mkt": [{"scope": "user", "installPath": str(cc / "cache" / "formatta")}],
        "vecchio@mkt": {"version": "1.0", "installPath": str(cc / "cache" / "vecchio")},
        "spento@mkt": [{"installPath": str(cc / "cache" / "spento")}]}}))
    (home / ".claude" / "settings.json").write_text(json.dumps({"enabledPlugins": {"spento@mkt": False}}))
    # un marketplace con un plugin locale e uno remoto (saltato)
    market = tmp_path / "market"
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [
        {"name": "traduci", "source": "./plugins/traduci"},
        {"name": "remoto", "source": {"source": "github", "repo": "x/y"}}]}))
    (market / "plugins" / "traduci" / "skills").mkdir(parents=True)
    monkeypatch.setenv("MYDEVAGENT_PLUGINS_DIRS", str(market))

    found = plugins.load_plugins(project)
    assert {n: p.source for n, p in found.items()} == {
        "revisore": "progetto", "formatta": "claude code", "vecchio": "claude code", "traduci": "extra"}
    rev = found["revisore"]
    assert (rev.count("commands"), rev.count("skills"), rev.count("agents")) == (1, 1, 1)
    assert rev.unsupported() == ["hook"] and rev.version == "1.2.0"

    skills = load_skills(project)
    assert skills["sicurezza"].source == skills["critico"].source == "plugin revisore"
    assert "Sei un revisore severo." in skills["critico"].read()
    assert skills_prompt(skills).endswith("- critico: Revisore severo.")  # niente esempi lunghi nel prompt

    desc, template = custom_commands(project)["/rivedi"]
    assert desc == "Rivede un file (plugin revisore)"
    root = project / ".mydevagent" / "plugins" / "revisore"
    assert expand_command(template, "app.py fai attenzione") == (
        f"Rivedi app.py con {root}/checklist.md. Note: app.py fai attenzione\n"
        "Stato: (run `git status` with your tools and use its output)")


def test_claude_code_commands_and_positional_args(tmp_path, home):
    project = tmp_path / "progetto"
    (project / ".claude" / "commands").mkdir(parents=True)
    (project / ".claude" / "commands" / "test.md").write_text("Esegui i test di $1")
    (home / ".claude" / "commands").mkdir(parents=True)
    (home / ".claude" / "commands" / "test.md").write_text("perde contro quello del progetto")
    desc, template = custom_commands(project)["/test"]
    assert desc == "comando personalizzato" and expand_command(template, "api") == "Esegui i test di api"
    assert expand_command("Spiega il codice", "src/app.py") == "Spiega il codice\n\nsrc/app.py"


def git(*args, cwd):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True,
                   capture_output=True)


def test_install_update_remove(tmp_path):
    repo = make_plugin(tmp_path / "repo" / "revisore-plugin")
    git("init", "-q", cwd=repo)
    git("add", ".", cwd=repo)
    git("commit", "-qm", "primo", cwd=repo)

    root = tmp_path / "progetto"
    [plugin] = plugins.install(repo.as_uri())  # URL git (file://): come un repo su GitHub
    assert plugin.name == "revisore" and plugin.source == "utente"
    assert plugin.path == tmp_path / "state" / "plugins" / "revisore-plugin"
    with pytest.raises(ValueError, match="già installato"):
        plugins.install(repo.as_uri())

    (repo / "commands" / "nuovo.md").write_text("nuovo comando")
    git("add", ".", cwd=repo)
    git("commit", "-qm", "secondo", cwd=repo)
    plugins.update("revisore", root)
    assert (plugin.path / "commands" / "nuovo.md").is_file()

    assert plugins.remove("revisore", root) == plugin.path and not plugin.path.exists()

    copied = plugins.install(str(repo))  # da una cartella: viene copiata, senza .git
    assert not (copied[0].path / ".git").exists()
    with pytest.raises(ValueError, match="reinstallalo"):
        plugins.update("revisore", root)
    plugins.remove("revisore", root)

    empty = tmp_path / "vuoto"
    empty.mkdir()
    with pytest.raises(ValueError, match="nessun plugin trovato"):
        plugins.install(str(empty))
    assert not (tmp_path / "state" / "plugins" / "vuoto").exists()

    make_plugin(root / ".mydevagent" / "plugins" / "locale", name="locale")
    for name, error in (("locale", "non è stato installato"), ("boh", "sconosciuto"), ("../x", "sconosciuto")):
        with pytest.raises(ValueError, match=error):
            plugins.remove(name, root)


def test_marketplace_folder_is_removed_as_a_whole(tmp_path):
    market = tmp_path / "negozio"
    (market / ".claude-plugin").mkdir(parents=True)
    (market / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [
        {"name": "a", "source": "./plugins/a"}, {"name": "b", "source": "./plugins/b"}]}))
    make_plugin(market / "plugins" / "a", name="a")
    make_plugin(market / "plugins" / "b", name="b")
    assert [p.name for p in plugins.install(str(market))] == ["a", "b"]
    root = tmp_path / "progetto"
    with pytest.raises(ValueError, match="/plugin remove negozio"):
        plugins.remove("a", root)
    assert plugins.remove("negozio", root).name == "negozio" and not plugins.load_plugins(root)
