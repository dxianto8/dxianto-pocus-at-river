"""
Vercel build step, run before a new deployment goes live:

1. Apply database migrations.
2. Create the first admin login from DJANGO_SUPERUSER_* settings, if one is set up and
   doesn't exist yet (see bookings/management/commands/ensure_admin.py).

Neon's Vercel integration provides two connection strings: DATABASE_URL goes through its
connection pooler, and DATABASE_URL_UNPOOLED connects directly. Schema changes should use the
direct connection, so this swaps it in for these commands only.

With Neon's preview branching, each preview deployment gets its own database branch, so
migrations in a pull request never touch the production database.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def manage(*args: str, env: dict[str, str]) -> None:
    subprocess.run([sys.executable, "manage.py", *args], cwd=ROOT, env=env, check=True)


def main() -> None:
    env = dict(os.environ)
    if env.get("DATABASE_URL_UNPOOLED"):
        env["DATABASE_URL"] = env["DATABASE_URL_UNPOOLED"]
    print("Applying database migrations...", flush=True)
    manage("migrate", "--noinput", env=env)
    print("Checking the admin login...", flush=True)
    manage("ensure_admin", env=env)


if __name__ == "__main__":
    main()
