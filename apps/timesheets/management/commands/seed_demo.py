"""A small kindergarten, so the app can be looked at rather than described.

Refuses to run with ``DEBUG`` off, and never touches a row it did not create.

The five contracts are chosen to cover the cases that *differ*, not to look
plausible — a seed where everybody works Monday to Friday hides every rule this
app has:

* **Anna** — five days, full time. The denominator everything else is measured
  against.
* **Ben** — four days, no Wednesday. His leave is four fifths of Anna's, and a
  Wednesday off costs him nothing. He is the manager.
* **Cem** — three days of unequal length (8, 8, 4). The case a "20 hours a week"
  field cannot express, and the reason the contract is seven columns.
* **Dilan** — five short days. Same working *days* as Anna and half the hours,
  so her leave is the same as Anna's — which is the pro-rata-by-days rule, and
  the thing that looks wrong until you know why.
* **Eva** — two days, and no account. She is what a roster looks like before
  somebody has ever signed in: the contract carries her directory name and the
  link is made the first time a token arrives with it.

The seeded week deliberately contains a day whose entered hours differ from the
roster, an overridden break, an approved holiday, a pending request and a sick
day. Every one of those is a state with its own rendering, and a seed without
them is a seed that makes the app look simpler than it is.
"""

import datetime as dt
from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from apps.absences.models import Absence, AbsenceKind, BankHoliday, RequestStatus
from apps.employees.models import Employee, SpecialLeaveGrant
from apps.organisation.models import (
    DEFAULT_BREAK_RULES, AssignmentMode, BreakRule, Land, OrgSettings,
    SpecialLeaveThreshold, SpecialLeaveType,
)
from apps.roster.models import Shift
from apps.timesheets.models import DayRecord, EntrySource, WorkSegment, week_monday

PASSWORD = "timetracking-dev-pass"


class Command(BaseCommand):
    help = "Create a demo organisation. DEBUG only."

    def handle(self, *args, **options):
        if not django_settings.DEBUG:
            raise CommandError(
                "seed_demo refuses to run with DEBUG off. It creates accounts with a "
                "known password."
            )

        # Worked out first, because the contracts need it: the opening balances
        # are dated at this week's Monday, which is the week the seed records.
        monday = week_monday(dt.date.today())

        settings = self._settings()
        types = self._leave_types()
        people = self._people(types, monday)
        self._holidays(settings)
        self._roster(people, monday)
        self._timesheets(people, monday, settings)
        self._absences(people, types, monday)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded. Sign in as anna / {PASSWORD} (employee, full time), "
            f"ben / {PASSWORD} (manager), or admin / {PASSWORD} (superuser)."
        ))

    # -- the rules -------------------------------------------------------

    def _settings(self):
        settings = OrgSettings.current()
        settings.full_time_days_per_week = 5
        settings.full_time_leave_days = Decimal("30.0")
        settings.land = Land.BW
        settings.day_start = dt.time(7, 30)
        settings.save()
        if not settings.break_rules.exists():
            BreakRule.objects.bulk_create([
                BreakRule(settings=settings, over_minutes=over, break_minutes=length)
                for over, length in DEFAULT_BREAK_RULES
            ])
        return settings

    def _leave_types(self):
        """One of each assignment mode, because the three give different answers
        and a seed with only the obvious one shows nothing."""
        birthday, _ = SpecialLeaveType.objects.get_or_create(
            name="Geburtstag",
            defaults={"mode": AssignmentMode.FIXED, "days": Decimal("1.0")},
        )
        long_service, _ = SpecialLeaveType.objects.get_or_create(
            name="Jubiläumstage",
            defaults={"mode": AssignmentMode.PRO_RATA, "days": Decimal("3.0")},
        )
        training, created = SpecialLeaveType.objects.get_or_create(
            name="Fortbildung",
            defaults={"mode": AssignmentMode.THRESHOLD, "days": Decimal("0")},
        )
        if created:
            # "Five days a week gets two, three days gets one" — and by
            # implication two days a week gets none, which is exactly what a
            # step table is for and what a pro-rata rule could not express.
            SpecialLeaveThreshold.objects.bulk_create([
                SpecialLeaveThreshold(leave_type=training, min_days_per_week=3, days=Decimal("1.0")),
                SpecialLeaveThreshold(leave_type=training, min_days_per_week=5, days=Decimal("2.0")),
            ])
        return {"birthday": birthday, "long_service": long_service, "training": training}

    # -- the people ------------------------------------------------------

    def _people(self, types, monday):
        self._account("admin", "Admin", superuser=True)

        people = {}
        # The local account name and the *directory* name are deliberately
        # different here — `anna` signs in locally, `anna.berger` is what LDAP
        # calls her — because that is the shape in the real deployment and a
        # seed where the two are equal would hide every place the app has to
        # know which is which.
        # The last two columns are what somebody *arrived* with: minutes of
        # hours, and days of leave. Two of the five carry a figure and in
        # opposite directions, because a seed where everybody starts at nought
        # hides the feature entirely and one where everybody starts in credit
        # hides the sign.
        contracts = [
            # local account, first, last, directory name, manager, the seven
            # days, opening minutes, opening leave days
            ("anna", "Anna", "Berger", "anna.berger", False, [8, 8, 8, 8, 8, 0, 0], 0, "0"),
            ("ben", "Ben", "Kraus", "ben.kraus", True, [8, 8, 0, 8, 8, 0, 0], 0, "0"),
            # Came across from another branch with hours in hand and leave not
            # yet taken — the ordinary case this exists for.
            ("cem", "Cem", "Yilmaz", "cem.yilmaz", False, [8, 8, 4, 0, 0, 0, 0], 14 * 60, "6.0"),
            # And the other direction: started in debit, which a field that only
            # took a positive number could not express.
            ("dilan", "Dilan", "Roth", "dilan.roth", False, [4, 4, 4, 4, 4, 0, 0], -3 * 60 - 30, "0"),
            # No account at all: what a roster looks like before somebody has
            # ever signed in, which is the state the whole nullable
            # Employee.user exists for.
            (None, "Eva", "Lang", "eva.lang", False, [0, 0, 6, 6, 0, 0, 0], 0, "0"),
        ]

        for (username, first, last, directory_name, manager, hours,
             opening_minutes, opening_leave) in contracts:
            user = self._account(username, first) if username else None
            employee, _created = Employee.objects.get_or_create(
                username=directory_name,
                defaults={
                    "first_name": first, "last_name": last,
                    "is_manager": manager, "user": user,
                    "started_on": dt.date.today() - dt.timedelta(days=400),
                },
            )
            employee.first_name, employee.last_name = first, last
            employee.is_manager, employee.user = manager, user
            employee.opening_balance_minutes = opening_minutes
            employee.opening_leave_days = Decimal(opening_leave)
            # **This week's Monday, not the day they started.** That is not a
            # fudge to make the demo look tidy — it is the real deployment
            # story, and the one the field exists for: these people have been
            # employed for over a year, and the app has been recording since
            # Monday. Dating the opening figure at their start date would ask
            # the running balance to account for four hundred days nobody
            # entered, and report everybody as two thousand hours short.
            #
            # An opening balance *is* the summary of everything before the app,
            # agreed with them. This is what that looks like.
            employee.opening_balance_on = monday
            employee.save()
            # The hours are a `ContractPeriod`, not seven columns on Employee.
            # setattr-ing `hours_mon` here used to work and now silently sets a
            # Python attribute that `save` ignores — which seeded everybody with
            # no contract at all and rendered as a demo full of zeros.
            employee.set_hours(
                [Decimal(str(value)) for value in hours],
                valid_from=employee.started_on,
            )
            people[first.lower()] = employee

        # Everybody gets the birthday; the three-day and five-day people get the
        # threshold type, so the list shows 2, 1 and 0 side by side.
        for employee in people.values():
            SpecialLeaveGrant.objects.get_or_create(
                employee=employee, leave_type=types["birthday"])
        for name in ("anna", "ben", "cem"):
            SpecialLeaveGrant.objects.get_or_create(
                employee=people[name], leave_type=types["training"])
        SpecialLeaveGrant.objects.get_or_create(
            employee=people["anna"], leave_type=types["long_service"])

        return people

    def _account(self, username, first, superuser=False):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={"first_name": first,
                      "is_staff": superuser, "is_superuser": superuser},
        )
        if created:
            user.set_password(PASSWORD)
            user.save()
        return user

    def _holidays(self, settings):
        year = dt.date.today().year
        for target in (year, year + 1):
            if not BankHoliday.objects.filter(date__year=target).exists():
                BankHoliday.generate(target, settings.land)

    # -- the week --------------------------------------------------------

    def _roster(self, people, monday):
        if Shift.objects.filter(date__gte=monday).exists():
            return
        shifts = []
        for employee in people.values():
            for offset in range(7):
                day = monday + dt.timedelta(days=offset)
                if not employee.works_on(day):
                    continue
                hours = float(employee.hours_on_weekday(day.weekday(), on=day))
                # A split shift for Cem on the Monday, because a kindergarten's
                # commonest shape is in for the morning and back for the late
                # afternoon — and a seed of single blocks hides that a day can
                # be two rows.
                if employee.first_name == "Cem" and day.weekday() == 0:
                    shifts.append(Shift(employee=employee, date=day,
                                        start=dt.time(7, 30), end=dt.time(11, 30),
                                        note="Gruppe 1"))
                    shifts.append(Shift(employee=employee, date=day,
                                        start=dt.time(14, 0), end=dt.time(18, 0),
                                        note="Spätdienst"))
                    continue
                span = int(hours * 60) + 30
                end = (7 * 60 + 30 + span) % (24 * 60)
                shifts.append(Shift(employee=employee, date=day,
                                    start=dt.time(7, 30),
                                    end=dt.time(end // 60, end % 60)))
        Shift.objects.bulk_create(shifts)

    def _timesheets(self, people, monday, settings):
        """Three states on purpose: confirmed as rostered, entered and
        different, and an overridden break."""
        rules = list(settings.break_rules.all())
        anna = people["anna"]
        for offset in (0, 1):
            day = monday + dt.timedelta(days=offset)
            if DayRecord.objects.filter(employee=anna, date=day).exists():
                continue
            DayRecord.from_shifts(
                anna, day, list(Shift.objects.filter(employee=anna, date=day)),
                by=anna.user, settings=settings, rules=rules,
            )

        # Ben stayed 90 minutes late on the Monday, so his day differs from the
        # roster — the one line a manager reads first on the team page.
        ben = people["ben"]
        day = monday
        if not DayRecord.objects.filter(employee=ben, date=day).exists():
            record = DayRecord.objects.create(
                employee=ben, date=day, source=EntrySource.MANUAL,
                note="Elterngespräch danach",
            )
            WorkSegment.objects.create(day=record, position=0,
                                       start=dt.time(7, 30), end=dt.time(17, 30))
            record.refresh_from_db()
            record.apply_break_rules(settings=settings, rules=rules)
            record.save()

        # Cem took an hour rather than the 45 minutes the rules give. Amber on
        # every page that shows it, which is the whole point of the column.
        cem = people["cem"]
        if not DayRecord.objects.filter(employee=cem, date=monday).exists():
            record = DayRecord.objects.create(
                employee=cem, date=monday, source=EntrySource.MANUAL,
                break_minutes=60, break_is_override=True,
            )
            WorkSegment.objects.create(day=record, position=0,
                                       start=dt.time(7, 30), end=dt.time(11, 30))
            WorkSegment.objects.create(day=record, position=1,
                                       start=dt.time(14, 0), end=dt.time(18, 0))

    def _absences(self, people, types, monday):
        if Absence.objects.exists():
            return
        # Approved holiday, next week.
        Absence.objects.create(
            employee=people["dilan"], kind=AbsenceKind.HOLIDAY,
            start_date=monday + dt.timedelta(days=7),
            end_date=monday + dt.timedelta(days=11),
            status=RequestStatus.APPROVED, reason="Kurzurlaub",
        )
        # Waiting for a decision, so the manager's page has something on it.
        Absence.objects.create(
            employee=people["cem"], kind=AbsenceKind.HOLIDAY,
            start_date=monday + dt.timedelta(days=14),
            end_date=monday + dt.timedelta(days=18),
            status=RequestStatus.REQUESTED, reason="Familienbesuch",
        )
        # Special leave against a named entitlement.
        Absence.objects.create(
            employee=people["anna"], kind=AbsenceKind.SPECIAL,
            special_type=types["training"],
            start_date=monday + dt.timedelta(days=21),
            end_date=monday + dt.timedelta(days=22),
            status=RequestStatus.REQUESTED, reason="Sprachförderung",
        )
        # Sickness: approved on arrival, costs no leave.
        Absence.objects.create(
            employee=people["eva"], kind=AbsenceKind.SICK,
            start_date=monday + dt.timedelta(days=2),
            end_date=monday + dt.timedelta(days=3),
            status=RequestStatus.APPROVED,
        )
