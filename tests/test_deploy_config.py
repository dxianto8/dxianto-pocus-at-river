"""Checks for the Vercel + Neon deployment setup."""

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def requirement_names(lines):
    return sorted(
        re.split(r"[=<>\[ ]", line.strip(), maxsplit=1)[0].lower()
        for line in lines
        if line.strip() and not line.startswith(("#", "-r"))
    )


def test_pyproject_lists_the_same_runtime_dependencies_as_requirements_txt():
    """Vercel installs from pyproject.toml, Docker from requirements.txt: keep them equal."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    from_pyproject = sorted(pyproject["project"]["dependencies"])
    from_requirements = sorted(
        line.strip()
        for line in (ROOT / "requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    )
    assert from_pyproject == from_requirements
    assert "django" in requirement_names(from_pyproject)


def test_python_version_is_pinned_for_vercel():
    assert (ROOT / ".python-version").read_text().strip() == "3.13"


def load_settings(**env) -> dict:
    """Import config.settings in a fresh process with the given environment."""
    clean = {k: v for k, v in os.environ.items() if not k.startswith(("DJANGO_", "VERCEL"))}
    clean.update(
        DATABASE_URL="postgres://user:pw@db.example.com:5432/app",
        DJANGO_SECRET_KEY="test-only-secret-key-0123456789abcdefghijklmnopqrstuvwxyz",
        **env,
    )
    code = (
        "import json; from config import settings as s; "
        "print(json.dumps({'hosts': s.ALLOWED_HOSTS, "
        "'conn_max_age': s.DATABASES['default']['CONN_MAX_AGE'], "
        "'no_server_cursors': s.DATABASES['default'].get('DISABLE_SERVER_SIDE_CURSORS')}))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=clean,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def test_on_vercel_accepts_vercel_hostnames_and_uses_short_lived_connections():
    settings = load_settings(VERCEL="1", DJANGO_ALLOWED_HOSTS="pocusatriver.com")
    assert ".vercel.app" in settings["hosts"]
    assert "pocusatriver.com" in settings["hosts"]
    assert settings["conn_max_age"] == 0


def test_elsewhere_keeps_persistent_connections_and_only_listed_hosts():
    settings = load_settings(DJANGO_ALLOWED_HOSTS="pocusatriver.com")
    assert settings["hosts"] == ["pocusatriver.com"]
    assert settings["conn_max_age"] == 600


def test_server_side_cursors_are_off_for_connection_poolers():
    assert load_settings()["no_server_cursors"] is True


def test_vercel_build_migrates_over_the_direct_connection():
    """Neon gives a pooled DATABASE_URL and a direct DATABASE_URL_UNPOOLED; schema changes
    use the direct one. The pooled URL here is unreachable, so success proves the direct one
    was used."""
    env = {
        **os.environ,
        "DATABASE_URL": "postgres://nobody:nothing@127.0.0.1:1/unreachable",
        "DATABASE_URL_UNPOOLED": os.environ["DATABASE_URL"],
    }
    result = subprocess.run(
        [sys.executable, "scripts/vercel_build.py"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "migrations" in result.stdout.lower()
