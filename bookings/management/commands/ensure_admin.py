"""
Create the first admin login from environment variables, so it can be set up from the
hosting dashboard (e.g. Vercel's Environment Variables) without running commands by hand.

    DJANGO_SUPERUSER_USERNAME   required to do anything
    DJANGO_SUPERUSER_PASSWORD   required to create the login; delete it once the login exists
    DJANGO_SUPERUSER_EMAIL      optional

Runs on every deploy, but only creates the login if that username doesn't exist yet. An
existing login is never changed, so a password changed in the admin stays changed.
"""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create the first admin login from DJANGO_SUPERUSER_* variables, if it doesn't exist."

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()

        if not username:
            self.stdout.write(
                "DJANGO_SUPERUSER_USERNAME isn't set, so not creating an admin login."
            )
            return

        User = get_user_model()
        if User.objects.filter(**{User.USERNAME_FIELD: username}).exists():
            self.stdout.write(f"Admin login '{username}' already exists; leaving it unchanged.")
            return

        if not password:
            raise CommandError(
                f"Set DJANGO_SUPERUSER_PASSWORD to create the admin login '{username}'."
            )
        user = User(**{User.USERNAME_FIELD: username}, email=email)
        try:
            validate_password(password, user)
        except ValidationError as error:
            raise CommandError(
                "DJANGO_SUPERUSER_PASSWORD isn't strong enough: " + " ".join(error.messages)
            ) from None

        User.objects.create_superuser(username, email, password)
        self.stdout.write(
            self.style.SUCCESS(
                f"Created admin login '{username}'. "
                "You can now delete DJANGO_SUPERUSER_PASSWORD from your hosting settings."
            )
        )
