# tests/test_inf4_startup.py
"""INF-4 — verify app.py exits with code 1 and friendly message when env vars missing."""
import subprocess
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def test_missing_secret_key():
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "APP_PASSWORD": "test"}
    result = subprocess.run(
        [sys.executable, "app.py"],
        capture_output=True,
        env=env,
        cwd=_PROJECT_ROOT,
    )
    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert b"SECRET_KEY is required" in output, (
        f"Expected 'SECRET_KEY is required' in output, got: {output!r}"
    )

def test_missing_app_password():
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "SECRET_KEY": "test-secret"}
    result = subprocess.run(
        [sys.executable, "app.py"],
        capture_output=True,
        env=env,
        cwd=_PROJECT_ROOT,
    )
    assert result.returncode == 1
    output = result.stdout + result.stderr
    assert b"APP_PASSWORD is required" in output, (
        f"Expected 'APP_PASSWORD is required' in output, got: {output!r}"
    )
