"""Day count conventions.

Three separate questions are answered here, and they are not the same question:

1. How many days lie between two dates?
2. Given a start date and a number of days, what is the end date?
3. How many days are in a year, for annualising an amount?

Under Actual conventions the answers come from the calendar. Under 30/360
conventions every month is treated as thirty days and every year as three
hundred and sixty, which is why a 30/360 term of 180 days lands exactly six
months out regardless of which months it crosses.

The 30/360 variants differ only in how they treat the thirty-first of a month
and the end of February. Those differences are small but they are real money on
a large balance, so each variant is implemented separately rather than
approximated.
"""

import calendar
from datetime import date

from frappe.utils import add_days, add_months, getdate

ACTUAL = "Actual (Calendar Days)"
ACT_365F = "Actual/365 Fixed"
ACT_360 = "Actual/360"
US_30_360 = "30/360 US"
EU_30E_360 = "30E/360 (Eurobond)"
ISDA_30E_360 = "30E/360 (ISDA)"

CONVENTIONS = [ACTUAL, ACT_365F, ACT_360, US_30_360, EU_30E_360, ISDA_30E_360]

# Conventions that count elapsed days from the calendar rather than in 30 day
# months. They differ from each other only in the year denominator.
ACTUAL_FAMILY = (ACTUAL, ACT_365F, ACT_360)

# Fixed year denominators. Actual (Calendar Days) has no fixed denominator; it
# uses the real length of the year being spanned.
YEAR_BASIS = {
    ACT_365F: 365,
    ACT_360: 360,
    US_30_360: 360,
    EU_30E_360: 360,
    ISDA_30E_360: 360,
}


def _last_day(year, month):
    return calendar.monthrange(year, month)[1]


def _is_last_of_month(d):
    return d.day == _last_day(d.year, d.month)


def _is_last_of_february(d):
    return d.month == 2 and _is_last_of_month(d)


# --------------------------------------------------------------- days between

def day_count(start, end, convention=ACTUAL, is_termination=True):
    """Days from start to end, exclusive of the end date.

    This is the market convention: a period running from 1 January to 1 February
    is 31 days, not 32. Use days_inclusive() when counting a term that occupies
    both endpoints.

    is_termination only affects 30E/360 ISDA, where the end of February is left
    uncollapsed when the date is the final maturity of the term and collapsed to
    the thirtieth when it is an interim period end. Every schedule period in
    this application is interim except the last, so the runner passes the flag
    accordingly. The default is the conservative reading.
    """
    start, end = getdate(start), getdate(end)

    if convention in ACTUAL_FAMILY:
        return (end - start).days

    d1, m1, y1 = start.day, start.month, start.year
    d2, m2, y2 = end.day, end.month, end.year

    if convention == US_30_360:
        # Bond basis. February end dates collapse to thirty, but only when both
        # ends of the period are February end dates.
        if _is_last_of_february(start) and _is_last_of_february(end):
            d2 = 30
        if _is_last_of_february(start):
            d1 = 30
        if d2 == 31 and d1 >= 30:
            d2 = 30
        if d1 == 31:
            d1 = 30

    elif convention == EU_30E_360:
        # Eurobond basis. The thirty-first becomes the thirtieth at both ends,
        # with no special treatment for February.
        if d1 == 31:
            d1 = 30
        if d2 == 31:
            d2 = 30

    elif convention == ISDA_30E_360:
        # The end of any month becomes the thirtieth. A February end date is
        # left alone only when it is the maturity of the term.
        if _is_last_of_month(start):
            d1 = 30
        if _is_last_of_month(end):
            if not (_is_last_of_february(end) and is_termination):
                d2 = 30

    return 360 * (y2 - y1) + 30 * (m2 - m1) + (d2 - d1)


def days_inclusive(start, end, convention=ACTUAL, is_termination=True):
    """Days occupied by a term that includes both the first and last day."""
    return day_count(start, end, convention, is_termination) + 1


# ------------------------------------------------------------- days to a date

def _add_30_360_days(start, n):
    """Advance a date by n days through a calendar of twelve thirty day months.

    Converting to a single day index and back keeps month rollover correct for
    any n, including values far larger than a year. A resulting day of 31 cannot
    occur; a day of 30 in February is clamped to the real month end, since no
    such calendar date exists.
    """
    start = getdate(start)
    d = 30 if start.day == 31 else start.day

    index = (start.year * 360) + ((start.month - 1) * 30) + (d - 1) + int(n)

    year, remainder = divmod(index, 360)
    month, day = divmod(remainder, 30)
    month += 1
    day += 1

    return date(year, month, min(day, _last_day(year, month)))


def end_date_from_days(start, number_of_days, convention=ACTUAL, inclusive=True):
    """Given a start date and a term in days, return the end date.

    inclusive means the start date itself counts as day one, which is how
    contract and lease terms are normally written. A 30 day term starting on
    1 August ends on 30 August when inclusive, and on 31 August when not.
    """
    start = getdate(start)
    n = int(number_of_days or 0)
    if n < 1:
        return start

    offset = n - 1 if inclusive else n

    if convention in ACTUAL_FAMILY:
        return getdate(add_days(start, offset))

    return _add_30_360_days(start, offset)


def days_from_end_date(start, end, convention=ACTUAL, inclusive=True):
    """Inverse of end_date_from_days. Useful for validating a hand-entered pair."""
    count = day_count(start, end, convention)
    return count + 1 if inclusive else count


# -------------------------------------------------------------- year basis

def year_length(convention=ACTUAL, reference_date=None):
    """Denominator for annualising an amount.

    Actual (Calendar Days) returns the real length of the year containing the
    reference date, so a leap year gives 366. Every other convention returns its
    fixed denominator.
    """
    if convention in YEAR_BASIS:
        return YEAR_BASIS[convention]

    ref = getdate(reference_date) if reference_date else getdate()
    return 366 if calendar.isleap(ref.year) else 365


# ------------------------------------------------------------ period helpers

def period_bounds(schedule_dates, term_end, convention=ACTUAL,
                  coverage_start=None, in_arrears=True):
    """Turn a list of posting dates into coverage windows.

    in_arrears, the normal case for an accrual or for amortising something
    already paid, means each period ENDS on its posting date. An entry dated
    31 July then covers July, which is what a month end accrual is for.

    in_arrears False means each period STARTS on its posting date, which suits
    rent or a subscription billed for the period ahead.

    coverage_start moves the beginning of the first window earlier than the
    first posting date. A prepayment made on the fifteenth and first posted at
    month end covers seventeen days in its first period, not one and not a
    whole month.

    Returns (start, end, days) tuples where days counts both endpoints.
    """
    out = []
    dates = [getdate(d) for d in schedule_dates]
    if not dates:
        return out

    term_end = getdate(term_end) if term_end else dates[-1]
    anchor = getdate(coverage_start) if coverage_start else dates[0]

    if in_arrears:
        previous = min(anchor, dates[0])
        for i, posting in enumerate(dates):
            start = previous
            end = term_end if i == len(dates) - 1 else posting
            if end < start:
                end = start
            out.append((start, end, days_inclusive(start, end, convention, i == len(dates) - 1)))
            previous = add_days(end, 1)
        return out

    for i, posting in enumerate(dates):
        start = min(anchor, posting) if i == 0 else posting
        end = add_days(dates[i + 1], -1) if i + 1 < len(dates) else term_end
        end = getdate(end)
        if end < start:
            end = start
        out.append((start, end, days_inclusive(start, end, convention, i == len(dates) - 1)))

    return out


def describe(convention):
    """One line explanation, shown as field help in the form."""
    return {
        ACTUAL: "Real calendar days. Year is 365, or 366 in a leap year.",
        ACT_365F: "Real calendar days elapsed, divided by a fixed 365 day year.",
        ACT_360: "Real calendar days elapsed, divided by a 360 day year. "
                 "Standard for money market and most bank facilities.",
        US_30_360: "Every month is 30 days, every year 360. Bond basis, with "
                   "February end dates collapsed to the thirtieth.",
        EU_30E_360: "Every month is 30 days, every year 360. The thirty-first "
                    "becomes the thirtieth at both ends of the period.",
        ISDA_30E_360: "Every month is 30 days, every year 360. Any month end "
                      "becomes the thirtieth, except February at maturity.",
    }.get(convention, "")
