# tests/test_inf4_startup.py
"""INF-4 — verify app.py exits with code 1 and friendly message when env vars missing."""
import subprocess
import sys
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# On Windows, user site-packages requires APPDATA to be discoverable.
# Pass through APPDATA (and USERPROFILE as fallback) so the subprocess
# can find packages installed to the user site-packages directory.
_BASE_ENV = {
    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    "DOTENV_DISABLED": "1",  # prevent load_dotenv from masking missing env vars in subprocess
}
if os.environ.get("APPDATA"):
    _BASE_ENV["APPDATA"] = os.environ["APPDATA"]
if os.environ.get("USERPROFILE"):
    _BASE_ENV["USERPROFILE"] = os.environ["USERPROFILE"]
if os.environ.get("SYSTEMROOT"):
    _BASE_ENV["SYSTEMROOT"] = os.environ["SYSTEMROOT"]


def test_missing_secret_key():
    env = {**_BASE_ENV, "APP_PASSWORD": "test"}
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
    env = {**_BASE_ENV, "SECRET_KEY": "test-secret"}
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
