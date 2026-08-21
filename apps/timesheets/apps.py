from django.apps import AppConfig
from django.db.backends.signals import connection_created


class TimesheetsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.timesheets"
    label = "timesheets"

    def ready(self):
        # Connected here rather than with an @receiver decorator: ready() is
        # the one point Django guarantees runs once, after the app registry is
        # populated. dispatch_uid so an autoreload that re-imports this module
        # does not stack a second copy of the handler onto every connection.
        connection_created.connect(_configure_sqlite, dispatch_uid="timesheets.sqlite_pragmas")


def _configure_sqlite(sender, connection, **kwargs):
    """WAL mode and a busy timeout, per connection.

    Both are per-*connection* PRAGMAs in SQLite, so setting them once at migrate
    time does nothing for the connections the server actually serves from. WAL
    is what lets a manager read the week's roster without blocking eleven people
    confirming yesterday's hours at the same time on their phones; without it
    the reader holds a shared lock and a writer comes back as "database is
    locked".

    That contention is not hypothetical. Confirmations arrive in a burst —
    everybody does it at the end of a shift, and a shift ends for everybody at
    once.

    ``synchronous=NORMAL`` is the WAL-mode recommendation: an OS crash can cost
    the last transaction, a *process* crash cannot. On a NAS with a UPS and a
    nightly Hyper Backup, that is the right trade for not fsyncing on every
    write.
    """
    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=20000;")
        # Off by default in SQLite, which means an on_delete=CASCADE that
        # Django did not itself emit is silently not enforced.
        cursor.execute("PRAGMA foreign_keys=ON;")
