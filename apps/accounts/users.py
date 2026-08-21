"""Managing the organisation's accounts, without the Django admin.

The admin can already do all of this, and it is still the wrong tool here. It
speaks in Django's vocabulary rather than the organisation's ("staff status",
"superuser status", a permissions box with sixty entries none of which this app
consults), it shows a Synology account under a username that is an opaque
``sub``, and it is a second interface with its own styling, its own navigation
and its own idea of what a dangerous action looks like. The admin stays
reachable for the things it is genuinely for — a bad row, a data fix — and the
everyday questions ("who is in the house, who has forgotten their password, who
has left") are answered here in the app's own pages.

**Authorisation is per view here, not by a list.** That is the opposite of the
rule in apps/accounts/pages.py, and the two are answering different questions.
Whether a page needs a *session* is a property of the whole app, so it is
enumerated centrally and fails towards refusal. Whether a signed-in member of
the organisation may see *these* pages is a property of the pages themselves —
same shape as ``apps/employees/permissions``. The exposure a forgotten
decorator would create is covered from the other side, by a test that walks the
URLconf and refuses to let any ``accounts:user-*`` route answer an ordinary
account.
"""

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.forms import (
    SetPasswordForm, UserCreateForm, UserEditForm, has_local_password,
    is_sso_account, sso_subject,
)
from apps.accounts.permissions import staff_required


@staff_required
def user_list(request):
    """Everybody this app knows about.

    Including the accounts that came in over SSO — but *only once they have
    signed in at least once*. This app has no directory to read: a DSM account
    exists here from the moment its first token arrives and not a second
    earlier, which is worth saying on the page rather than leaving somebody to
    wonder where their sister is.
    """
    people = list(
        User.objects
        # The identity row, so that `is_sso_account` below is free rather than
        # a query per person — it reads the relation, and an uncached reverse
        # one-to-one fetches.
        .select_related("sso_identity")
        # The employee row behind the account, which is the one thing this page
        # can say that the Employees page cannot: an account with no contract
        # is a normal state (an administrator who does not work shifts) and an
        # employee with no account is another (somebody who has not signed in
        # yet). Only this page sees both sides at once.
        .select_related("employee")
        .order_by("-is_active", "first_name", "username")
    )
    for person in people:
        # A template cannot call has_usable_password() with an argument and a
        # property on the model would mean subclassing User for one boolean.
        person.is_sso = is_sso_account(person)
        # No longer the opposite of the line above: an account that has been
        # linked is both, and the page has to be able to say so.
        person.has_password = has_local_password(person)
        person.sso_subject = sso_subject(person)

    return render(request, "accounts/user_list.html", {
        "people": people,
        "active_count": sum(1 for p in people if p.is_active),
        "sso_count": sum(1 for p in people if p.is_sso),
    })


@staff_required
def user_add(request):
    if request.method == "POST":
        form = UserCreateForm(request.POST, editor=request.user)
        if form.is_valid():
            person = form.save()
            messages.success(request, _("The account “%(name)s” was created.") % {
                "name": person.get_username(),
            })
            return redirect("accounts:user-list")
    else:
        form = UserCreateForm(editor=request.user, initial={"is_active": True})

    return render(request, "accounts/user_form.html", {
        "form": form, "person": None, "is_sso": False,
    })


@staff_required
def user_edit(request, pk):
    person = get_object_or_404(User, pk=pk)

    if request.method == "POST":
        form = UserEditForm(request.POST, instance=person, editor=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, _("“%(name)s” was saved.") % {
                "name": person.get_full_name() or person.get_username(),
            })
            return redirect("accounts:user-list")
    else:
        form = UserEditForm(instance=person, editor=request.user)

    return render(request, "accounts/user_form.html", {
        "form": form, "person": person,
        "is_sso": is_sso_account(person),
        "has_password": has_local_password(person),
        "sso_subject": sso_subject(person),
    })


@staff_required
def user_password(request, pk):
    """Set a new password — for an account that has one.

    A Synology account has no usable password on purpose, and giving it one
    here would quietly create the second, unmanaged door into a DSM-managed
    identity that the whole SSO arrangement exists to avoid. So this is a 404
    for those, not a disabled button.

    The test is "has a password", not "is not an SSO account", and since
    linking those are no longer the same question: a linked account already has
    a local password by definition, and refusing to *change* it would be a
    organisation locked out of its own fallback the day the provider is down.
    """
    person = get_object_or_404(User, pk=pk)
    if not has_local_password(person):
        raise Http404

    if request.method == "POST":
        form = SetPasswordForm(request.POST, account=person)
        if form.is_valid():
            person.set_password(form.cleaned_data["password1"])
            person.save(update_fields=["password"])
            if person.pk == request.user.pk:
                # Changing your own password rotates the session hash, which
                # signs you out of the page you are standing on. This keeps the
                # current session valid; every other one still ends.
                update_session_auth_hash(request, person)
            messages.success(request, _("The password for “%(name)s” was changed.") % {
                "name": person.get_username(),
            })
            return redirect("accounts:user-list")
    else:
        form = SetPasswordForm(account=person)

    return render(request, "accounts/user_password.html", {
        "form": form, "person": person,
    })


@staff_required
@require_POST
def user_unlink_sso(request, pk):
    """Detach the identity provider from an account.

    The counterpart to the automatic link, and the reason the link is allowed
    to be automatic at all. Everything else on these pages is somebody pressing
    something; attaching a DSM identity to an existing account happens on its
    own, by e-mail address, and an automatic action with no undo is not one
    this app should be taking. See ``SynologyOIDCBackend._account_to_link``.

    Refused for an account with no local password, and that is the same door
    rule as the rest of this file: unlinking one would leave an account with no
    way in at all. Those are unlinked by deleting them.

    The next token carrying that ``sub`` gets an account of its own — or links
    again, if the address still matches. Changing one of the two first is the
    point of doing this at all.
    """
    person = get_object_or_404(User, pk=pk)
    name = person.get_full_name() or person.get_username()

    if not has_local_password(person):
        messages.error(request, _(
            "“%(name)s” has no password of their own, so single sign-on is the "
            "only way in. Delete the account instead."
        ) % {"name": name})
        return redirect("accounts:user-list")

    identity = getattr(person, "sso_identity", None)
    if identity is None:
        messages.error(request, _("“%(name)s” is not linked to the identity provider.") % {
            "name": name,
        })
        return redirect("accounts:user-list")

    identity.delete()
    messages.success(request, _(
        "“%(name)s” is no longer linked to the identity provider and signs in "
        "with their password."
    ) % {"name": name})
    return redirect("accounts:user-edit", pk=person.pk)


@staff_required
@require_POST
def user_delete(request, pk):
    """Remove an account outright.

    Offered alongside "switch off", not instead of it, because the two mean
    different things: somebody who has left the organisation is deactivated and
    keeps everything; a row created by a mistyped username is deleted.

    **Deleting an account never takes a timesheet with it.**
    ``Employee.user`` is ``SET_NULL``, so the employee record and every hour on
    it survive — the two are simply no longer linked. That is deliberate and it
    is the whole reason the two are separate tables: somebody who has left still
    worked those hours, payroll may need them for years afterwards, and an app
    that discarded them because an account was tidied up would be destroying the
    only record of it.

    What is lost is the link itself, which cannot be guessed back: the next time
    that person signs in they arrive as a new account, and a manager has to
    attach them to their employee row by hand. That is the reason "switch off"
    is offered first.
    """
    person = get_object_or_404(User, pk=pk)

    if person.pk == request.user.pk:
        messages.error(request, _("You cannot delete your own account."))
        return redirect("accounts:user-list")

    last_administrator = (
        person.is_superuser
        and not User.objects.filter(is_superuser=True, is_active=True)
        .exclude(pk=person.pk).exists()
    )
    if last_administrator:
        messages.error(request, _(
            "This is the last active administrator. Give somebody else the right first."
        ))
        return redirect("accounts:user-list")

    name = person.get_full_name() or person.get_username()
    with transaction.atomic():
        person.delete()
    messages.success(request, _("“%(name)s” was deleted.") % {"name": name})
    return redirect("accounts:user-list")


@staff_required
@require_POST
def user_toggle_active(request, pk):
    """The one-click version of "they have left" / "they are back".

    Deactivating is the *reversible* answer, which is why it is a button on the
    list and deleting is not: an account switched off keeps its name on every
    hour it recorded and can be switched back on. A DSM account that has
    been disabled upstream also lands here — the login is refused by Synology
    either way, and this is how somebody records it locally.
    """
    person = get_object_or_404(User, pk=pk)

    if person.pk == request.user.pk:
        messages.error(request, _("You cannot switch off your own account."))
        return redirect("accounts:user-list")

    if person.is_active and person.is_superuser and not User.objects.filter(
        is_superuser=True, is_active=True
    ).exclude(pk=person.pk).exists():
        messages.error(request, _(
            "This is the last active administrator. Give somebody else the right first."
        ))
        return redirect("accounts:user-list")

    person.is_active = not person.is_active
    person.save(update_fields=["is_active"])
    messages.success(
        request,
        (_("“%(name)s” can sign in again.") if person.is_active
         else _("“%(name)s” can no longer sign in.")) % {
            "name": person.get_full_name() or person.get_username(),
        },
    )
    return redirect("accounts:user-list")
