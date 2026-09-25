import importlib.util
import subprocess
import sys

import pytest

from mydevagent import templates, update


def test_target_folder_rules(tmp_path, monkeypatch):
    empty = tmp_path / "vuota"
    empty.mkdir()
    assert templates.target_for(empty, "sito") == empty  # cartella vuota: il progetto nasce lì
    work = tmp_path / "lavori"
    (work / "api").mkdir(parents=True)
    (work / "api" / "main.py").write_text("x = 1\n")
    assert templates.target_for(work, "api") == work / "api-2"
    assert templates.target_for(work, "api", "mia-api") == work / "mia-api"
    with pytest.raises(ValueError):
        templates.target_for(work, "api", "api")  # esiste già e non è vuota
    with pytest.raises(ValueError):
        templates.target_for(work, "api", "../fuori")
    monkeypatch.setattr(update, "HOME", work)
    assert templates.target_for(work, "sito") == tmp_path / "sito"  # mai dentro la cartella di MyDevAgent


@pytest.mark.parametrize("kind", list(templates.TEMPLATES))
def test_templates_are_ready_to_use(kind, tmp_path):
    dest = tmp_path / kind
    created = templates.create(kind, dest)
    assert "MYDEVAGENT.md" in created and ".gitignore" in created
    assert not any(name in created for name in templates.DOTFILES)  # rinominati con il punto
    for path in dest.rglob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")
    if kind == "sito":
        html = (dest / "index.html").read_text(encoding="utf-8")
        assert "style.css" in html and "script.js" in html
    needs = {"python": "pytest", "api": "fastapi"}
    if kind in needs and importlib.util.find_spec(needs[kind]):
        tests = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=dest,
                               capture_output=True, text=True, timeout=120)
        assert tests.returncode == 0, tests.stdout + tests.stderr
