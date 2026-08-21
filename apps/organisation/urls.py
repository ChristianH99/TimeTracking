"""The working time rules. Every route here is staff-only, enforced by the
decorator on each view rather than here — ``apps/organisation/tests.py`` walks
this file and refuses to let any of them answer an ordinary account, which is
what covers the one somebody forgets."""

from django.urls import path

from apps.organisation import views

app_name = "organisation"

urlpatterns = [
    path("", views.settings_view, name="settings"),
    path("breaks/defaults/", views.install_default_break_rules, name="break-rules"),

    path("leave-types/", views.leave_types, name="leave-types"),
    path("leave-types/new/", views.leave_type_form, name="leave-type-add"),
    path("leave-types/<int:pk>/", views.leave_type_form, name="leave-type-edit"),
    path("leave-types/<int:pk>/delete/", views.leave_type_delete, name="leave-type-delete"),

    path("holidays/", views.holidays, name="holidays"),
    path("holidays/generate/", views.holidays_generate, name="holidays-generate"),

    path("closures/", views.closures, name="closures"),
    path("closures/new/", views.closure_form, name="closure-add"),
    path("closures/<int:pk>/", views.closure_form, name="closure-edit"),
    path("closures/<int:pk>/delete/", views.closure_delete, name="closure-delete"),
]
