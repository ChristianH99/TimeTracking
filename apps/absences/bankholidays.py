"""The German public holidays, computed rather than tabulated.

Thirteen days, of which four move with Easter and one moves with the calendar.
Nine of the thirteen depend on the Land, which is why ``OrgSettings.land`` is a
required setting: an app that assumed Bavaria would hand every employee in
Hamburg Fronleichnam, Mariä Himmelfahrt and Allerheiligen — three days they do
not have — and the error shows up as somebody marked absent on a day they were
expected at work.

**Why this is ninety lines of arithmetic and not a dependency.** A holiday table
somebody else maintains is a table that goes stale silently: it is right for the
years it shipped with, and the first January nobody upgrades, every Karfreitag
in the app is simply missing. The computation has no release cadence to track,
and it is pinned by a test naming real dates for real years — which is a check
on *this* code that a version bump cannot invalidate.

**What this deliberately does not model.** Fronleichnam is a public holiday in
parts of Saxony and Thuringia, and Mariä Himmelfahrt in the Catholic
municipalities of Bavaria — both at *municipal* level, decided by where the town
hall is rather than by the Land. This app answers at Land level and stops there.
Getting it wrong at municipal level is a real possibility for a business in one
of those four Länder, so ``generate`` writes rows somebody can edit and delete
rather than computing on the fly: the calculation is a good first draft and the
administrator has the last word. That is the whole reason ``BankHoliday`` is a
table at all rather than a function.
"""

import datetime as dt

from apps.organisation.models import Land

# Which Länder observe each of the nine regional days. Written as the full set
# for each holiday rather than as a per-Land list, because that is the direction
# the sources state it in and a transposed table is one nobody can check against
# them.
_CATHOLIC_SOUTH = frozenset({Land.BW, Land.BY, Land.HE, Land.NW, Land.RP, Land.SL})
_PROTESTANT_NORTH_EAST = frozenset({
    Land.BB, Land.HB, Land.HH, Land.MV, Land.NI, Land.SH, Land.SN, Land.ST, Land.TH,
})


def easter_sunday(year):
    """Gregorian Easter, by the anonymous algorithm.

    Four of the thirteen holidays are offsets from this date and a fifth and
    sixth (Ostersonntag and Pfingstsonntag, in Brandenburg) are it and one of
    the offsets. Getting it wrong moves a quarter of the year's holidays at
    once, which is why the test names Easter for five known years rather than
    checking that the function returns a Sunday.
    """
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month, day = divmod(h + el - 7 * m + 114, 31)
    return dt.date(year, month, day + 1)


def repentance_day(year):
    """Buß- und Bettag: the Wednesday before 23 November. Saxony only.

    The one holiday that is neither a fixed date nor an Easter offset. Counted
    back from the 22nd rather than forward from the 16th, because "the Wednesday
    before the 23rd" is what the statute says and a nearest-Wednesday reading
    lands a week early in the years when the 23rd is itself a Wednesday.
    """
    reference = dt.date(year, 11, 22)
    # date.weekday(): Monday is 0, so Wednesday is 2.
    return reference - dt.timedelta(days=(reference.weekday() - 2) % 7)


def holidays(year, land):
    """``[(date, name), …]`` for one year in one Land, in calendar order.

    Names are German because that is what they are called on a German rota, and
    a translated "Corpus Christi" is a day nobody recognises. They are stored as
    written rather than as keys into a catalogue for the same reason the rows
    are editable: an administrator who has to correct one should be able to see
    what they are correcting.
    """
    easter = easter_sunday(year)
    days = [
        (dt.date(year, 1, 1), "Neujahr"),
        (easter - dt.timedelta(days=2), "Karfreitag"),
        (easter + dt.timedelta(days=1), "Ostermontag"),
        (dt.date(year, 5, 1), "Tag der Arbeit"),
        (easter + dt.timedelta(days=39), "Christi Himmelfahrt"),
        (easter + dt.timedelta(days=50), "Pfingstmontag"),
        (dt.date(year, 10, 3), "Tag der Deutschen Einheit"),
        (dt.date(year, 12, 25), "1. Weihnachtstag"),
        (dt.date(year, 12, 26), "2. Weihnachtstag"),
    ]

    if land in {Land.BW, Land.BY, Land.ST}:
        days.append((dt.date(year, 1, 6), "Heilige Drei Könige"))
    if land in {Land.BE, Land.MV}:
        days.append((dt.date(year, 3, 8), "Internationaler Frauentag"))
    if land == Land.BB:
        # Brandenburg is the only Land where the two Sundays are themselves
        # public holidays. It changes nothing for a Monday-to-Friday business
        # and everything for one that opens at the weekend, which is why it is
        # here rather than dismissed as a technicality.
        days.append((easter, "Ostersonntag"))
        days.append((easter + dt.timedelta(days=49), "Pfingstsonntag"))
    if land in _CATHOLIC_SOUTH:
        days.append((easter + dt.timedelta(days=60), "Fronleichnam"))
    if land == Land.SL:
        days.append((dt.date(year, 8, 15), "Mariä Himmelfahrt"))
    if land == Land.TH:
        days.append((dt.date(year, 9, 20), "Weltkindertag"))
    if land in _PROTESTANT_NORTH_EAST:
        days.append((dt.date(year, 10, 31), "Reformationstag"))
    if land in {Land.BW, Land.BY, Land.NW, Land.RP, Land.SL}:
        days.append((dt.date(year, 11, 1), "Allerheiligen"))
    if land == Land.SN:
        days.append((repentance_day(year), "Buß- und Bettag"))

    return sorted(days)
