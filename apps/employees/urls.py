"""The employee list and the contract behind each person.

Manager-only, enforced per view. ``apps/employees/tests.py`` walks this module
and refuses to let any route here answer an ordinary employee — which is what
covers the decorator somebody forgets on the next one they add.
"""

from django.urls import path

from apps.employees import views

app_name = "employees"

urlpatterns = [
    path("", views.employee_list, name="list"),
    path("new/", views.employee_form, name="add"),
    path("<int:pk>/", views.employee_form, name="edit"),
    path("<int:pk>/delete/", views.employee_delete, name="delete"),
    path("<int:pk>/leave/", views.employee_leave, name="leave"),
    path("<int:pk>/contract/", views.contract_change, name="contract-change"),
    path("<int:pk>/contract/<int:period_pk>/delete/", views.contract_delete,
         name="contract-delete"),
]
