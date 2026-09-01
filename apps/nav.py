"""Which sidebar entry is the current page.

The obvious version of this lives in the template — each entry comparing
``request.resolver_match.url_name`` against the name it expects. It works until
two apps use the same ``url_name``, which they will (``list``, ``detail``,
``settings`` are nobody's private words, and here three apps have a ``week``),
and then two entries light up at once and the bug is invisible until somebody
notices the sidebar looks odd.

So the mapping lives here, keyed on the ``(app_name, url_name)`` *pair* Django
has already resolved. Two properties make the whole class of bug go away, and
``config/tests.py::TestTheSidebarMarksOnePage`` holds both:

* the sets are pairwise disjoint, so no URL can mark two entries;
* every pair named here exists in the URLconf, so a renamed route fails a test
  instead of quietly marking nothing.

The sign-in pages (``accounts:login``/``logout``) are deliberately absent: the
user block sits in the sidebar footer, outside the nav, and is never marked.
The account *management* pages are here — being staff-only is a question for
the template, not for this file.
"""

# Sidebar entry id -> the (app_name, url_name) pairs that make it current.
# Dotted ids are nested under the parent named before the dot.
ITEMS = {
    "home": {("timesheets", "home")},

    # A person's own pages. `mine` is the timesheet; `day` is one day of it,
    # which is where confirming and manual entry both happen.
    "mine.timesheet": {
        ("timesheets", name)
        for name in ("mine", "save-day", "set-status", "confirm-week", "day",
                     "confirm-day", "clock")
    },
    "mine.absences": {
        ("absences", name)
        for name in ("mine", "request", "request-cancel", "sick", "sick-end")
    },

    # The manager's pages. Note that `timesheets:employee-day` is here and
    # `timesheets:day` is above, while both resolve to one view: the same
    # rendering of two different questions, and marking "My time" because a
    # manager opened somebody else's Tuesday is exactly the bug this file exists
    # to prevent. apps/timesheets/urls.py says why the route is duplicated.
    "team.roster": {
        ("roster", name)
        for name in ("plan", "save", "copy-week", "shift-delete", "fill-from-pattern")
    },
    "team.timesheets": {
        ("timesheets", name)
        for name in ("team", "employee", "employee-save-day", "employee-set-status",
                     "employee-day", "employee-confirm-day", "employee-clock")
    },
    # Closing a month, beside closing a year. Both are periodic acts a manager
    # performs over everybody at once, and neither belongs inside the page for
    # one person's timesheet.
    "team.month-end": {
        ("timesheets", name)
        for name in ("month-end", "lock-month", "lock-day")
    },
    "team.requests": {
        ("absences", name) for name in ("requests", "decide")
    },
    "team.year-end": {
        ("absences", name)
        for name in ("year-end", "close-year", "expire-year", "extend-deadline")
    },
    "team.employees": {
        ("employees", name)
        for name in ("list", "add", "edit", "delete", "leave",
                     "contract-change", "contract-delete")
    },

    # "My settings" is for everybody; the rest are staff- and superuser-only and
    # the sidebar hides them accordingly. They are all registered here all the
    # same, because "which entry is current" and "who may see the entry" are
    # different questions, and conflating them is how an entry ends up marked on
    # a page nobody can reach.
    "settings.rules": {
        ("organisation", name)
        for name in ("settings", "break-rules", "leave-types", "leave-type-add",
                     "leave-type-edit", "leave-type-delete", "holidays",
                     "holidays-generate", "closures", "closure-add",
                     "closure-edit", "closure-delete")
    },
    "settings.users": {
        ("accounts", name)
        for name in ("user-list", "user-add", "user-edit", "user-password",
                     "user-delete", "user-active")
    },
    "settings.sso": {("accounts", name) for name in ("sso", "sso-discover", "sso-check")},
}

# Parent entry -> the entries nested under it. A parent is a link too, but never
# to a page of its own: it is marked when any of its children is.
#
# "settings" is the odd one out and deliberately so: it is a *disclosure* in the
# sidebar footer rather than a link, holding the pages that are about the app
# rather than about the work. It still appears here, because the group has to
# open by itself when one of the pages inside it is the current one — a menu
# that hides the page you are looking at is a menu that looks broken.
PARENTS = {
    "mine": ("mine.timesheet", "mine.absences"),
    "team": ("team.roster", "team.timesheets", "team.month-end", "team.requests",
             "team.employees",
             "team.year-end"),
    "settings": ("settings.rules", "settings.users", "settings.sso"),
}


def current(match):
    """The sidebar entries a resolved URL marks: the entry itself and, when it
    is nested, its parent. Empty for a page with no entry — or an unresolved
    one, which is the case on an error page."""
    if match is None:
        return frozenset()
    key = (match.app_name, match.url_name)
    active = {name for name, urls in ITEMS.items() if key in urls}
    for parent, children in PARENTS.items():
        if not active.isdisjoint(children):
            active.add(parent)
    return frozenset(active)


def context(request):
    """Template context processor: ``nav_current``, which base.html asks with
    ``{% if 'team.roster' in nav_current %}``."""
    return {"nav_current": current(getattr(request, "resolver_match", None))}
