"""Three routes onto one list.

``mine`` and ``employee`` resolve to the same page and differ only in their
path, the same duplication ``apps/timesheets/urls.py`` carries and for the same
reason: ``apps/nav.py`` keys the sidebar on the resolved ``(app, url_name)``
pair, so one shared route would light "My time" while a manager was reading
somebody else's history. The prefix is presentation; ``own_or_manager`` in the
view is the check.
"""

from django.urls import path

from apps.audit import views

app_name = "audit"

urlpatterns = [
    # The whole table, sign-ins included. Staff only — this is the software
    # administrator's page and the one an auditor is shown.
    path("", views.log, name="log"),
    # Your own history, reached from your own timesheet.
    path("mine/", views.mine, name="mine"),
    # Somebody else's, reached from theirs. A manager opening it is itself a
    # read, and `own_or_manager` records it.
    path("employee/<int:pk>/", views.employee_log, name="employee"),
]
