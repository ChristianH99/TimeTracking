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
    # The area dialog in a time range's menu. JSON in and out, so an area can be
    # added half-way through planning a week without saving or losing the week.
    path("areas/new/", views.area_save, name="area-new"),
    path("areas/<int:pk>/", views.area_save, name="area-save"),
    path("areas/<int:pk>/delete/", views.area_delete, name="area-delete"),
]
