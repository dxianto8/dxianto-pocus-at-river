import importlib.util
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parent.parent
STRONG = "river-motors-1924-reception"


@pytest.fixture
def admin_env(monkeypatch):
    def set_env(username="owner", password=STRONG, email="owner@example.com"):
        for name, value in [
            ("DJANGO_SUPERUSER_USERNAME", username),
            ("DJANGO_SUPERUSER_PASSWORD", password),
            ("DJANGO_SUPERUSER_EMAIL", email),
        ]:
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)

    for name in (
        "DJANGO_SUPERUSER_USERNAME",
        "DJANGO_SUPERUSER_PASSWORD",
        "DJANGO_SUPERUSER_EMAIL",
    ):
        monkeypatch.delenv(name, raising=False)
    return set_env


def run(capsys) -> str:
    call_command("ensure_admin")
    return capsys.readouterr().out


def test_creates_the_admin_login_from_settings(admin_env, capsys):
    admin_env()
    out = run(capsys)
    user = get_user_model().objects.get(username="owner")
    assert user.is_staff and user.is_superuser
    assert user.email == "owner@example.com"
    assert user.check_password(STRONG)
    assert "Created admin login 'owner'" in out
    assert STRONG not in out  # never print the password


def test_existing_login_is_left_alone(admin_env, capsys):
    get_user_model().objects.create_superuser(
        "owner", "owner@example.com", "the-original-password-77"
    )
    admin_env(password="a-different-password-99")
    out = run(capsys)
    assert get_user_model().objects.get(username="owner").check_password("the-original-password-77")
    assert "already exists" in out


def test_does_nothing_without_a_username(admin_env, capsys):
    admin_env(username=None, password=None, email=None)
    out = run(capsys)
    assert not get_user_model().objects.exists()
    assert "not creating" in out.lower()


def test_missing_password_fails_clearly(admin_env):
    admin_env(password=None)
    with pytest.raises(CommandError, match="DJANGO_SUPERUSER_PASSWORD"):
        call_command("ensure_admin")
    assert not get_user_model().objects.exists()


@pytest.mark.parametrize("weak", ["owner", "password", "12345678", "short"])
def test_weak_password_fails_clearly(admin_env, weak):
    admin_env(password=weak)
    with pytest.raises(CommandError, match="isn't strong enough"):
        call_command("ensure_admin")
    assert not get_user_model().objects.exists()


def test_email_is_optional(admin_env, capsys):
    admin_env(email=None)
    run(capsys)
    assert get_user_model().objects.get(username="owner").email == ""


def test_vercel_build_migrates_then_ensures_the_admin(monkeypatch):
    spec = importlib.util.spec_from_file_location("vercel_build", ROOT / "scripts/vercel_build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)

    calls = []
    monkeypatch.setattr(build.subprocess, "run", lambda cmd, **kw: calls.append((cmd, kw["env"])))
    monkeypatch.setenv("DATABASE_URL", "postgres://pooled")
    monkeypatch.setenv("DATABASE_URL_UNPOOLED", "postgres://direct")
    build.main()

    assert [cmd[2:] for cmd, _ in calls] == [["migrate", "--noinput"], ["ensure_admin"]]
    assert all(env["DATABASE_URL"] == "postgres://direct" for _, env in calls)
