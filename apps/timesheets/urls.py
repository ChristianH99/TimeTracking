"""The timesheet, and the app's start page.

Included last in ``config/urls.py`` because it owns the root.

**One day view, two routes.** ``day`` and ``employee-day`` — and likewise the
two save routes — resolve to one function each and differ only in their prefix,
and that duplication is doing real work: ``apps/nav.py`` keys the sidebar on the resolved ``(app, url_name)`` pair,
so a single shared route would light "My time" while a manager was looking at
somebody else's Tuesday. Both are gated by ``own_or_manager`` in the view — the
prefix is presentation, and the check is not.
"""

from django.urls import path

from apps.timesheets import views

app_name = "timesheets"

urlpatterns = [
    path("", views.home, name="home"),

    # A person's own time. `mine` is the month; the month it shows comes from
    # ?month=YYYY-MM rather than from the path, so that every link into it — a
    # redirect after a save, the dropdown, the two arrows — is the same URL with
    # one parameter changed.
    path("timesheet/", views.mine, name="mine"),
    # One day at a time, answering with the month. There is no Save button on
    # the timesheet: a box that is left or a pop-up that is accepted writes that
    # day, and the reply is the whole month recomputed — see views.save_day.
    path("timesheet/save/<str:date>/", views.save_day_mine, name="save-day"),
    # A status — sick, a day off, time in lieu — set from the timesheet's own
    # status cell rather than from the absences page. A form POST and a redirect,
    # not the JSON the rest of the page uses: a status changes what the whole
    # month is worth, and a reload is both simpler and certainly right.
    path("timesheet/status/<str:date>/", views.set_status_mine, name="set-status"),
    path("timesheet/confirm-week/", views.confirm_week, name="confirm-week"),
    path("timesheet/<int:pk>/clock/", views.clock, name="clock"),
    path("timesheet/<int:pk>/<str:date>/", views.day, name="day"),
    path("timesheet/<int:pk>/<str:date>/confirm/", views.confirm_day, name="confirm-day"),

    # The manager's view of everybody else's.
    path("team/", views.team, name="team"),
    path("team/<int:pk>/", views.employee_month, name="employee"),
    path("team/<int:pk>/save/<str:date>/", views.save_day, name="employee-save-day"),
    path("team/<int:pk>/status/<str:date>/", views.set_status, name="employee-set-status"),
    path("team/<int:pk>/clock/", views.clock, name="employee-clock"),
    path("team/<int:pk>/<str:date>/", views.day, name="employee-day"),
    path("team/<int:pk>/<str:date>/confirm/", views.confirm_day, name="employee-confirm-day"),
]
