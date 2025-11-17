import secrets
import string
from dataclasses import dataclass
from typing import Iterable, List

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from portal.constants import iter_committees


@dataclass(frozen=True)
class AccountSpec:
    username: str
    full_name: str
    email: str


def _random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%?-_"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _iter_account_specs(domain: str) -> Iterable[AccountSpec]:
    def make_email(username: str) -> str:
        return f"{username}@{domain}".lower()

    yield AccountSpec("union_president", "Union President", make_email("union_president"))
    yield AccountSpec("union_vice_president", "Union Vice President", make_email("union_vice_president"))

    for committee in iter_committees():
        username = f"{committee.key}_lead"
        full_name = f"{committee.name} Lead"
        yield AccountSpec(username, full_name, make_email(username))

    for idx in range(1, 3):
        username = f"operations_admin_{idx:02d}"
        full_name = f"Operations Center Admin {idx:02d}"
        yield AccountSpec(username, full_name, make_email(username))

    for idx in range(1, 3):
        username = f"media_admin_{idx:02d}"
        full_name = f"Media Admin {idx:02d}"
        yield AccountSpec(username, full_name, make_email(username))

    yield AccountSpec("dev_admin", "Development Admin", make_email("dev_admin"))


class Command(BaseCommand):
    help = "Create or refresh the named admin accounts for union leadership and committees."

    def add_arguments(self, parser):
        parser.add_argument(
            "--password",
            type=str,
            help="Password applied to all created or updated accounts (default: generate unique random passwords).",
        )
        parser.add_argument(
            "--domain",
            type=str,
            default="vc29.local",
            help="Email domain for generated accounts (default: vc29.local).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the actions without touching the database.",
        )

    def handle(self, *args, **options):
        password_override = options.get("password")
        domain = options["domain"].strip() or "vc29.local"
        dry_run = options["dry_run"]

        user_model = get_user_model()

        created: List[str] = []
        updated: List[str] = []
        skipped: List[str] = []
        credentials_output: List[str] = []

        for spec in _iter_account_specs(domain):
            password = password_override or _random_password()
            user = user_model.objects.filter(username=spec.username).first()

            if user is None:
                if dry_run:
                    created.append(spec.username)
                    if not password_override:
                        credentials_output.append(f"  - {spec.username} / {password}")
                    else:
                        credentials_output.append(f"  - {spec.username} / (provided password)")
                    continue

                user = user_model.objects.create_user(
                    username=spec.username,
                    email=spec.email,
                    password=password,
                    full_name=spec.full_name,
                )
                user.is_staff = True
                user.is_superuser = True
                user.save(update_fields=["is_staff", "is_superuser"])
                created.append(spec.username)
                if password_override:
                    credentials_output.append(f"  - {spec.username} / (provided password)")
                else:
                    credentials_output.append(f"  - {spec.username} / {password}")
                continue

            changed = False
            fields_to_update: List[str] = []

            if user.full_name != spec.full_name:
                user.full_name = spec.full_name
                fields_to_update.append("full_name")
                changed = True
            if user.email != spec.email:
                user.email = spec.email
                fields_to_update.append("email")
                changed = True
            if not user.is_staff:
                user.is_staff = True
                fields_to_update.append("is_staff")
                changed = True
            if not user.is_superuser:
                user.is_superuser = True
                fields_to_update.append("is_superuser")
                changed = True

            if password_override:
                user.set_password(password_override)
                fields_to_update.append("password")
                changed = True

            if dry_run:
                if changed:
                    updated.append(spec.username)
                else:
                    skipped.append(spec.username)
                continue

            if changed:
                unique_fields = sorted(set(fields_to_update))
                if unique_fields:
                    user.save(update_fields=unique_fields)
                else:
                    user.save()
                updated.append(spec.username)
            else:
                skipped.append(spec.username)

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run mode; no accounts were modified."))

        if created:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Accounts to be created:"))
            for username in created:
                self.stdout.write(f"  - {username}")

        if updated:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Accounts to be updated:"))
            for username in updated:
                self.stdout.write(f"  - {username}")

        if skipped:
            self.stdout.write("")
            self.stdout.write("Accounts already up to date:")
            for username in skipped:
                self.stdout.write(f"  - {username}")

        if credentials_output and not dry_run:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Credentials for newly created accounts:"))
            for line in credentials_output:
                self.stdout.write(line)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Done."))
