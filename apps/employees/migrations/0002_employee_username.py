"""Replace ``Employee.email`` with ``Employee.username``.

Written by hand rather than generated, because the generated version cannot do
the middle step: the new column is **unique and not null**, so it has to arrive
empty, be filled from what is already there, and only then have the constraint
put on it. A generated migration would ask for a one-size default and give every
row the same value, which a unique index then refuses.

The backfill takes the local part of the old address (``anna.berger@…`` ->
``anna.berger``) because in practice that *is* the directory name — the same
LDAP account generates both. Where there was no address it falls back to
``firstname.surname``, and where even that collides it appends a number. None of
those is guaranteed right, which is why the operation logs nothing and the
People page shows the value: it is a starting point a manager corrects, not an
answer.
"""

from django.db import migrations, models
import django.db.models.functions.text


def fill_usernames(apps, schema_editor):
    Employee = apps.get_model("employees", "Employee")
    from apps.employees.models import Employee as Live

    taken = set()
    for employee in Employee.objects.all().order_by("pk"):
        address = (employee.email or "").strip()
        candidate = address.split("@", 1)[0].lower() if address else ""
        if not candidate:
            candidate = Live.suggest_username(employee.first_name, employee.last_name)
        candidate = candidate or f"employee{employee.pk}"

        unique = candidate
        suffix = 2
        while unique in taken:
            unique = f"{candidate}{suffix}"
            suffix += 1
        taken.add(unique)

        employee.username = unique
        employee.save(update_fields=["username"])


def restore_emails(apps, schema_editor):
    """Reversing puts the name back where the address was.

    Lossy and stated as such: the original address is gone. It is enough to let
    a rollback leave a working database rather than an empty column, which is
    the whole job of a reverse operation.
    """
    Employee = apps.get_model("employees", "Employee")
    for employee in Employee.objects.all():
        employee.email = employee.username
        employee.save(update_fields=["email"])


class Migration(migrations.Migration):

    dependencies = [("employees", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="employee",
            name="username",
            field=models.CharField(
                blank=True, default="", max_length=150,
                verbose_name="sign-in name",
            ),
        ),
        migrations.RunPython(fill_usernames, restore_emails),
        migrations.AlterField(
            model_name="employee",
            name="username",
            field=models.CharField(
                help_text=(
                    "The name from the directory — usually firstname.surname. This is "
                    "what recognises them the first time they sign in."
                ),
                max_length=150, unique=True, verbose_name="sign-in name",
            ),
        ),
        migrations.AddConstraint(
            model_name="employee",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("username"),
                name="one_employee_per_sign_in_name",
            ),
        ),
        migrations.RemoveField(model_name="employee", name="email"),
    ]
