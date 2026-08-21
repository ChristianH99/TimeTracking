"""Move the seven hour columns off ``Employee`` and onto ``ContractPeriod``.

**The order of the three steps is the whole migration.** Django's own guess put
the ``RemoveField``s first, which drops every contract in the database and then
creates an empty table to hold them — a migration that runs cleanly, reports
success, and leaves every employee on no hours at all. Nothing raises, because
"no hours" is a state the app can render: it renders as a page of zeros.

So: create the table, copy each employee's columns into one period dated from
the day they started, *then* drop the columns.

``valid_from`` for an employee with no start date is 1 January 2000, which is
early enough that no date this app will ever be asked about falls before it. It
is not ``date.min`` because a date in the year 1 renders on the contract page,
and "in force from 01.01.0001" is the sort of thing somebody opens a ticket
about.

The reverse writes the columns back from whichever period was in force, so that
downgrading loses the *history* — which it must, there being nowhere to put it —
and not the contract.
"""


import django.core.validators
import django.db.models.deletion
from decimal import Decimal
import datetime as dt

from django.db import migrations, models


# The earliest date any period is dated from when the employee has no start
# date of their own. Early enough that nothing is uncovered; late enough to be
# a date a human recognises.
EPOCH = dt.date(2000, 1, 1)

HOURS = ("hours_mon", "hours_tue", "hours_wed", "hours_thu",
         "hours_fri", "hours_sat", "hours_sun")


def to_periods(apps, schema_editor):
    """One period per employee, carrying what the columns said."""
    Employee = apps.get_model("employees", "Employee")
    ContractPeriod = apps.get_model("employees", "ContractPeriod")
    rows = [
        ContractPeriod(
            employee=person,
            valid_from=person.started_on or EPOCH,
            note="",
            **{name: getattr(person, name) for name in HOURS},
        )
        for person in Employee.objects.all()
    ]
    ContractPeriod.objects.bulk_create(rows)


def from_periods(apps, schema_editor):
    """Write the contract in force back onto the columns.

    Loses the history, which is unavoidable — there is nowhere on ``Employee``
    to put a second set of hours. Takes the *latest* period rather than the one
    in force today, because a downgrade that dropped a change already agreed for
    next month would be losing a decision somebody made.
    """
    Employee = apps.get_model("employees", "Employee")
    ContractPeriod = apps.get_model("employees", "ContractPeriod")
    for person in Employee.objects.all():
        period = (
            ContractPeriod.objects.filter(employee=person)
            .order_by("-valid_from").first()
        )
        if period is None:
            continue
        for name in HOURS:
            setattr(person, name, getattr(period, name))
        person.save(update_fields=list(HOURS))


class Migration(migrations.Migration):

    dependencies = [
        ('employees', '0003_employee_time_zone'),
    ]

    operations = [
        migrations.CreateModel(
            name='ContractPeriod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valid_from', models.DateField(help_text='The first date these hours apply. Everything before it keeps the previous ones.', verbose_name='in force from')),
                ('hours_mon', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='Monday')),
                ('hours_tue', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='Tuesday')),
                ('hours_wed', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='Wednesday')),
                ('hours_thu', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='Thursday')),
                ('hours_fri', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='Friday')),
                ('hours_sat', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='Saturday')),
                ('hours_sun', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=4, validators=[django.core.validators.MinValueValidator(Decimal('0')), django.core.validators.MaxValueValidator(Decimal('24'))], verbose_name='Sunday')),
                ('note', models.CharField(blank=True, help_text='Shown beside the change on their contract — “went to three days”, “parental leave”.', max_length=200, verbose_name='why it changed')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('employee', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contract_periods', to='employees.employee', verbose_name='employee')),
            ],
            options={
                'verbose_name': 'contract',
                'verbose_name_plural': 'contracts',
                'ordering': ['-valid_from'],
                'constraints': [models.UniqueConstraint(fields=('employee', 'valid_from'), name='one_contract_per_start_date')],
            },
        ),
        migrations.RunPython(to_periods, from_periods),
        migrations.RemoveField(
            model_name='employee',
            name='hours_fri',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='hours_mon',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='hours_sat',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='hours_sun',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='hours_thu',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='hours_tue',
        ),
        migrations.RemoveField(
            model_name='employee',
            name='hours_wed',
        ),
    ]
