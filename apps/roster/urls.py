"""The week planner. Manager-only, enforced per view."""

from django.urls import path

from apps.roster import views

app_name = "roster"

urlpatterns = [
    path("", views.plan, name="plan"),
    # The planner posts back to itself, so `save` is the same view. It is named
    # separately all the same, because apps/nav.py keys the sidebar on the
    # resolved url_name and a POST that resolved to nothing would leave the
    # Team section unmarked on the page somebody just saved.
    path("save/", views.plan, name="save"),
    path("copy/", views.copy_week, name="copy-week"),
    path("fill/", views.fill_from_pattern, name="fill-from-pattern"),
    path("<int:pk>/delete/", views.shift_delete, name="shift-delete"),
]
