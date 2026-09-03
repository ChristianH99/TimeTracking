from django.apps import AppConfig


class AuditConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.audit"
    label = "audit"

    def ready(self):
        """Connect both halves of the trail.

        In ``ready`` rather than at import time, and with a ``dispatch_uid`` on
        every receiver — the same shape ``apps/timesheets/apps.py`` uses for the
        SQLite pragmas, and for the same reason: ``ready`` is the one point
        Django guarantees runs once with the app registry populated, and the uid
        stops an autoreload that re-imports the module from stacking a second
        copy of every handler onto every save. Two copies would write every
        entry twice, which reads as the app having done the thing twice.
        """
        from apps.audit import access, signals

        signals.connect()
        access.connect()
