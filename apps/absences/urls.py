"""Time off. The first three are anybody's own; the rest are manager-only,
enforced per view.

``book`` is one route for a day off, hours taken back and an illness alike —
the calendar's pop-up offers all three from one set of radio buttons, and a
dialog that had to post to a different URL depending on which one was ticked is
a dialog with two ways to be wrong. It replaced ``request`` and ``sick``, which
differed only in the form they built; the *forms* are still two, and
``views.book`` says why that is where the difference belongs.
"""

from django.urls import path

from apps.absences import views

app_name = "absences"

urlpatterns = [
    path("", views.mine, name="mine"),
    path("book/", views.book, name="book"),
    path("request/<int:pk>/withdraw/", views.request_cancel, name="request-cancel"),

    path("requests/", views.requests, name="requests"),
    path("requests/<int:pk>/decide/", views.decide, name="decide"),

    # The end of a leave year: what is carried, what lapses, and who was told.
    path("year-end/", views.year_end, name="year-end"),
    path("year-end/close/", views.close_year, name="close-year"),
    path("year-end/expire/", views.expire_year, name="expire-year"),
    path("year-end/<int:pk>/extend/", views.extend_deadline, name="extend-deadline"),
]
