"""Give every shift written before the grid a slot to be drawn in.

Without this, every week planned before the grid opens as an empty grid with
the shifts still in the database — invisible on the page that plans them and
still read by the timesheet, which is the worst combination: the manager plans
the week again on top of them and everybody is rostered twice.

Each distinct start–end pair in a week becomes a slot, and each Monday–Friday
shift is placed in the slot of its own times, so nothing about what anybody was
asked to work changes. Weekend shifts are left without a slot, because the grid
has no weekend columns and a slot owning them would take them with it the day
the manager removed that row.
"""

from django.db import migrations

import datetime as dt


def forwards(apps, schema_editor):
    Shift = apps.get_model("roster", "Shift")
    TimeSlot = apps.get_model("roster", "TimeSlot")
    PlannedWeek = apps.get_model("roster", "PlannedWeek")

    slots = {}
    for shift in Shift.objects.filter(slot__isnull=True).order_by("date", "start"):
        if shift.date.weekday() >= 5:
            continue
        monday = shift.date - dt.timedelta(days=shift.date.weekday())
        key = (monday, shift.start, shift.end)
        if key not in slots:
            slots[key] = TimeSlot.objects.create(week=monday, start=shift.start, end=shift.end)
        shift.slot = slots[key]
        shift.save(update_fields=["slot"])

    # Those weeks were planned, and must not be offered a copy of another week
    # on top of what they already hold.
    for monday in {key[0] for key in slots}:
        PlannedWeek.objects.get_or_create(week=monday)


def backwards(apps, schema_editor):
    # Detach rather than delete: the shifts are the plan and must survive the
    # slots going away. Removing the slots themselves is the schema migration's
    # job on the way down.
    Shift = apps.get_model("roster", "Shift")
    Shift.objects.update(slot=None)
    apps.get_model("roster", "PlannedWeek").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("roster", "0002_grid"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
