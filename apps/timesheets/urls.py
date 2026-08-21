"""The timesheet, and the app's start page.

Included last in ``config/urls.py`` because it owns the root.

**One day view, two routes.** ``day`` and ``employee-day`` resolve to the same
function and differ only in their prefix, and that duplication is doing real
work: ``apps/nav.py`` keys the sidebar on the resolved ``(app, url_name)`` pair,
so a single shared route would light "My time" while a manager was looking at
somebody else's Tuesday. Both are gated by ``own_or_manager`` in the view — the
prefix is presentation, and the check is not.
"""

from django.urls import path

from apps.timesheets import views

app_name = "timesheets"

urlpatterns = [
    path("", views.home, name="home"),

    # A person's own time.
    path("timesheet/", views.mine, name="mine"),
    path("timesheet/confirm-week/", views.confirm_week, name="confirm-week"),
    path("timesheet/<int:pk>/clock/", views.clock, name="clock"),
    path("timesheet/<int:pk>/<str:date>/", views.day, name="day"),
    path("timesheet/<int:pk>/<str:date>/confirm/", views.confirm_day, name="confirm-day"),

    # The manager's view of everybody else's.
    path("team/", views.team, name="team"),
    path("team/<int:pk>/", views.employee_week, name="employee"),
    path("team/<int:pk>/clock/", views.clock, name="employee-clock"),
    path("team/<int:pk>/<str:date>/", views.day, name="employee-day"),
    path("team/<int:pk>/<str:date>/confirm/", views.confirm_day, name="employee-confirm-day"),
]
