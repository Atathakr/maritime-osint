# tests/test_inf3_anthropic.py
"""INF-3 — verify anthropic SDK is not in requirements or source files."""
import pathlib
import os

_PROJECT_ROOT = pathlib.Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_anthropic_not_in_requirements():
    req = (_PROJECT_ROOT / "requirements.txt").read_text()
    assert "anthropic" not in req, "anthropic found in requirements.txt — remove it"

def test_anthropic_not_in_pyproject():
    pyp = (_PROJECT_ROOT / "pyproject.toml").read_text()
    assert "anthropic" not in pyp, "anthropic found in pyproject.toml — remove it"

def test_no_anthropic_imports():
    src_files = list(_PROJECT_ROOT.glob("*.py"))
    for f in src_files:
        if ".venv" in str(f) or "site-packages" in str(f):
            continue
        content = f.read_text(errors="ignore")
        assert "import anthropic" not in content, f"{f} contains 'import anthropic'"
        assert "from anthropic" not in content, f"{f} contains 'from anthropic'"
