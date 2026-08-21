"""Close a leave year, and optionally let the carried days lapse.

The same two acts as the Year end page, offered on the command line because they
are the two things somebody will want to put in a scheduled task on the NAS —
close on 1 January, expire on 1 April — and because a page that has to be
clicked once a year is a page nobody remembers exists.

    uv run python manage.py close_leave_year 2025
    uv run python manage.py close_leave_year 2025 --notice 2025-11-15
    uv run python manage.py close_leave_year 2025 --expire

**It refuses to expire a deadline that has not passed**, exactly as the page
does. The days belong to the employee until the morning after, and there is no
undo for taking them away — a `--force` that skipped that check would exist for
nobody's benefit.
"""

import datetime as dt

from django.core.management.base import BaseCommand, CommandError

from apps.absences.carryover import LeaveCarryOver, expire_due
from apps.employees.models import Employee
from apps.organisation.models import OrgSettings


class Command(BaseCommand):
    help = "Carry each employee's remaining leave into the next year."

    def add_arguments(self, parser):
        parser.add_argument(
            "year", type=int,
            help="The year that has ended. Days left in it are carried into the next.",
        )
        parser.add_argument(
            "--notice", default=None,
            help=(
                "The date the team was told what they had left and that it would "
                "lapse (YYYY-MM-DD). Without it the statutory days are recorded as "
                "not expiring — which is what German case law says they do."
            ),
        )
        parser.add_argument(
            "--expire", action="store_true",
            help="Also write off carried days whose deadline has passed.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Say what would happen and change nothing.",
        )

    def handle(self, *args, **options):
        year = options["year"]
        if not 1970 <= year <= 2200:
            raise CommandError(f"{year} is not a year this app can close.")

        notice = None
        if options["notice"]:
            try:
                notice = dt.date.fromisoformat(options["notice"])
            except ValueError as error:
                raise CommandError(
                    f"--notice {options['notice']!r} is not a date. Use YYYY-MM-DD."
                ) from error

        settings = OrgSettings.current()
        dry = options["dry_run"]

        carried = 0
        for employee in Employee.objects.filter(is_active=True):
            if dry:
                from apps.absences.models import Balance

                left = Balance(employee, year, settings).remaining
                if left > 0:
                    carried += 1
                    self.stdout.write(f"  {employee.full_name}: {left} day(s) would carry")
                continue
            if LeaveCarryOver.close_year(employee, year, settings, notice_given_on=notice):
                carried += 1

        verb = "would carry" if dry else "are carrying"
        self.stdout.write(self.style.SUCCESS(
            f"{carried} people {verb} days into {year + 1}."
        ))
        if notice is None and not dry:
            self.stdout.write(self.style.WARNING(
                "No reminder date was given, so the statutory days are recorded as not "
                "expiring. That is the safe answer and it is also the legally correct "
                "one until each person has been told — pass --notice once they have."
            ))

        if not options["expire"]:
            return

        today = dt.date.today()
        deadline = settings.statutory_deadline(year + 1)
        if today <= deadline:
            raise CommandError(
                f"The deadline is {deadline:%d.%m.%Y} and it has not passed. Those "
                "days are still theirs to take."
            )
        if dry:
            self.stdout.write("(dry run: nothing was written off)")
            return

        lost = expire_due(year + 1, on=today, settings=settings)
        self.stdout.write(self.style.SUCCESS(
            f"{len(lost)} people lost carried-over days."
        ))
