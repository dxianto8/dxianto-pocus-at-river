"""
Vercel build step: apply database migrations before a new deployment goes live.

Neon's Vercel integration provides two connection strings: DATABASE_URL goes through its
connection pooler, and DATABASE_URL_UNPOOLED connects directly. Schema changes should use the
direct connection, so this swaps it in for the migrate command only.

With Neon's preview branching, each preview deployment gets its own database branch, so
migrations in a pull request never touch the production database.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    env = dict(os.environ)
    if env.get("DATABASE_URL_UNPOOLED"):
        env["DATABASE_URL"] = env["DATABASE_URL_UNPOOLED"]
    print("Applying database migrations...", flush=True)
    subprocess.run(
        [sys.executable, "manage.py", "migrate", "--noinput"], cwd=ROOT, env=env, check=True
    )


if __name__ == "__main__":
    main()
