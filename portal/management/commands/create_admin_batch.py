import secrets
import string
from typing import List, Tuple

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


def _random_password(length: int = 14) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%?-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


class Command(BaseCommand):
    help = "Create or update a batch of staff/superuser accounts."

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Number of admin accounts to ensure exist (default: 10).",
        )
        parser.add_argument(
            "--prefix",
            type=str,
            default="admin",
            help="Prefix used when generating usernames (default: 'admin').",
        )
        parser.add_argument(
            "--password",
            type=str,
            help="Password to assign to all created accounts. If omitted, unique passwords are generated and displayed.",
        )
        parser.add_argument(
            "--domain",
            type=str,
            default="vc29.local",
            help="Domain portion used for generated email addresses (default: vc29.local).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show the accounts that would be created without writing to the database.",
        )

    def handle(self, *args, **options):
        count = options["count"]
        prefix = options["prefix"].strip()
        password_override = options.get("password")
        domain = options["domain"].strip()
        dry_run = options["dry_run"]
        user_model = get_user_model()

        if count <= 0:
            raise CommandError("--count must be a positive integer.")
        if not prefix:
            raise CommandError("--prefix cannot be empty.")
        if not domain:
            raise CommandError("--domain cannot be empty.")

        padding = max(2, len(str(count)))
        created: List[Tuple[str, str]] = []
        skipped: List[str] = []

        for idx in range(1, count + 1):
            username = f"{prefix}{idx:0{padding}d}"
            password = password_override or _random_password()
            email = f"{username}@{domain}"

            user = user_model.objects.filter(username=username).first()
            if user:
                skipped.append(username)
                continue

            if dry_run:
                created.append((username, password))
                continue

            user = user_model.objects.create_user(
                username=username,
                email=email,
                password=password,
                full_name=f"Admin {idx:0{padding}d}",
            )
            user.is_staff = True
            user.is_superuser = True
            user.save(update_fields=["is_staff", "is_superuser"])

            created.append((username, password))

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run mode; no accounts were created."))

        if created:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Created admin accounts:"))
            for username, password in created:
                if password_override:
                    password_display = "(provided password)"
                else:
                    password_display = password
                self.stdout.write(f"  - {username} / {password_display}")
        else:
            self.stdout.write("No new admin accounts were created.")

        if skipped:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Skipped existing usernames:"))
            for username in skipped:
                self.stdout.write(f"  - {username}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done."))
