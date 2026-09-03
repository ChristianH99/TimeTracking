"""Delete what is out of its retention period, or say what would go.

    uv run python manage.py apply_retention            # says what would go
    uv run python manage.py apply_retention --apply    # actually deletes

**A dry run by default, and there is no way to make deletion the default.** This
is the one command in the app that destroys records somebody may be asked for,
and the two spellings are one word apart — so the word has to be typed. A
scheduled task on the NAS carries `--apply`; a person finding out what the policy
would do does not, and cannot get it wrong by leaving an argument off.

The same rows a person reads before pressing the button are computed by the same
code that the button runs (`apps/audit/retention.py::survey` and `sweep` share
their matchers), because a dry run that took a different path would be reassuring
about something else.

**It writes one audit entry per class**, not one per row: a sweep of ten years
would otherwise fill the trail with entries about records that no longer exist,
and grow the table it was shrinking. See `apps/audit/signals.suppressed`.
"""

from django.core.management.base import BaseCommand

from apps.audit import retention
from apps.organisation.models import OrgSettings


class Command(BaseCommand):
    help = "Delete records whose retention period has expired."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help=(
                "Actually delete. Without it nothing is touched and the command "
                "only reports what is out of period."
            ),
        )

    def handle(self, *args, **options):
        settings = OrgSettings.current()
        rows = retention.survey(settings)
        applying = options["apply"]

        self.stdout.write("")
        for row in rows:
            years = f"{row['years']}a" if row["years"] is not None else "—"
            cutoff = f"before {row['cutoff']:%d.%m.%Y}" if row["cutoff"] else "when nothing is left"
            oldest = f", oldest {row['oldest']:%d.%m.%Y}" if row["oldest"] else ""
            floor_note = ""
            if row["raised_to_floor"]:
                # Said out loud rather than silently obeyed. A setting the app
                # overrides without a word is a setting somebody believes.
                floor_note = self.style.WARNING(
                    f"  [set to {row['wanted']}a, raised to the statutory {row['floor']}a]"
                )
            self.stdout.write(
                f"  {str(row['label']):<26} {years:>4}  {cutoff:<28}"
                f" {row['due']:>7} due{oldest}{floor_note}"
            )

        total = sum(row["due"] for row in rows)
        self.stdout.write("")
        if not total:
            self.stdout.write(self.style.SUCCESS("Nothing is out of its retention period."))
            return

        if not applying:
            self.stdout.write(self.style.WARNING(
                f"{total} records are out of period. Nothing was deleted — "
                "run again with --apply to remove them."
            ))
            return

        removed = retention.sweep(settings, dry_run=False)
        gone = sum(row["total"] for row in removed)
        self.stdout.write(self.style.SUCCESS(
            f"{gone} records were deleted. One audit entry per class records what went."
        ))
