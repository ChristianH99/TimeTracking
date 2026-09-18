"""Which models are evidence, and which deliberately are not.

**A list, and a test that walks every model in the project against it.** The
same shape as ``apps/accounts/pages.py``: a model has to be named in one of the
three sets below or ``apps/audit/tests.py`` fails, so a table added next month is
a decision somebody makes rather than a gap nobody notices. The failure mode of
the alternative — a decorator, a mixin, a base class somebody remembers to
inherit — is a new model that is silently outside the trail and looks completely
normal.

Three sets and not two, because "audited" has two shapes here.

``BY_SIGNAL`` is the ordinary one: a row changed, and the entry is the diff.

``BY_HAND`` is for the handful whose **natural unit is larger than a row**.
Locking a month writes thirty-one ``DayLock``s in one gesture; regenerating a
year writes thirteen ``BankHoliday``s. Signalling each of them would be
technically complete and practically useless — the one sentence somebody needs
("Ben closed September for Anna") would be buried under thirty rows saying the
same thing about consecutive dates. These write **one** entry, from the view
that performs the act, and the test holds them to having a writer.

``EXEMPT`` is the interesting column, as usual. Each entry says why.
"""

# Diffed automatically by apps/audit/signals.py.
BY_SIGNAL = {
    # The timesheet itself: the reason this whole app exists.
    "timesheets.DayRecord",
    # Every punch. **Its ``bulk_create`` call sites were changed to ordinary
    # saves** so that this is true — see `DayRecord.set_bookings`. `bulk_create`
    # fires no `post_save` at all, and a trail that captured the deletes and not
    # the creates would show every edit as the day being emptied.
    "timesheets.WorkSegment",

    # What was booked off, and every decision on it.
    "absences.Absence",
    "absences.CompanyClosure",
    "absences.LeaveCarryOver",

    # Who somebody is, and what they were contracted to work. `ContractPeriod`
    # already keeps its own history — this records who wrote that history.
    "employees.Employee",
    "employees.ContractPeriod",
    "employees.SpecialLeaveGrant",

    # The rules every figure in the app is computed against. A month that added
    # up last year and does not now has usually had one of these edited, and
    # without this there is nothing on the page to say so.
    "organisation.OrgSettings",
    "organisation.BreakRule",
    "organisation.SpecialLeaveType",
    "organisation.SpecialLeaveThreshold",

    # The plan. Kept in because "what were you asked to work" is half of the
    # sentence this app exists to be able to say (BAG 5 AZR 359/21), and a
    # roster edited after the fact is exactly the half somebody would dispute.
    # It is cheaper than it looks: an entry is written only when something
    # actually changed, and the roster's save posts the whole week every time.
    "roster.Shift",

    # How everybody authenticates, and who holds the client secret. Audited
    # with the secret **redacted** — see `models.REDACTED_HINTS`. Recording
    # that it changed is the point; recording what to would put every secret the
    # installation ever had into the one table nothing can delete.
    "accounts.SSOConfiguration",
}

# One entry per act, written by the view that performs it.
BY_HAND = {
    # A month is what a manager closes. `apps/timesheets/views.py::lock_month`
    # and `lock_day` write it.
    "timesheets.DayLock",
    # A year is what somebody regenerates. `apps/organisation/views.py`.
    "absences.BankHoliday",
}

# Deliberately outside the trail. The reason is the column that matters.
EXEMPT = {
    # Auditing the audit log is a loop, and the table refuses to be changed
    # anyway — which is a stronger guarantee than a trail of its own would be.
    "audit.AuditEntry",

    # Written by the identity provider on every single sign-in, with a token
    # that would then be sitting in a table nothing deletes. The sign-in itself
    # is already an entry, which is the fact anybody actually asks about.
    "accounts.SSOIdentity",

    # Django's own. The account model is covered from the other side — every
    # sign-in, refusal and sign-out is an entry — and sessions, permissions,
    # content types and the admin's own log are the framework's furniture
    # rather than this business's records.
    "auth.User",
    "auth.Group",
    "auth.Permission",
    "admin.LogEntry",
    "contenttypes.ContentType",
    "sessions.Session",
}


def label_of(model):
    """``"timesheets.DayRecord"`` for a model class or instance."""
    meta = model._meta
    return f"{meta.app_label}.{meta.object_name}"


def all_declared():
    return BY_SIGNAL | BY_HAND | EXEMPT
