"""Time off. The first five are anybody's own; the last two are manager-only,
enforced per view."""

from django.urls import path

from apps.absences import views

app_name = "absences"

urlpatterns = [
    path("", views.mine, name="mine"),
    path("request/", views.request_absence, name="request"),
    path("request/<int:pk>/withdraw/", views.request_cancel, name="request-cancel"),
    path("sick/", views.report_sick, name="sick"),
    path("sick/<int:pk>/end/", views.end_sickness, name="sick-end"),

    path("requests/", views.requests, name="requests"),
    path("requests/<int:pk>/decide/", views.decide, name="decide"),

    # The end of a leave year: what is carried, what lapses, and who was told.
    path("year-end/", views.year_end, name="year-end"),
    path("year-end/close/", views.close_year, name="close-year"),
    path("year-end/expire/", views.expire_year, name="expire-year"),
    path("year-end/<int:pk>/extend/", views.extend_deadline, name="extend-deadline"),
]
