"""Date generation for a repeat rhythm expressed as a count and a unit."""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, get_last_day, getdate

UNIT_DAYS = {"Day": 1, "Week": 7}
UNIT_MONTHS = {"Month": 1, "Quarter": 3, "Year": 12}


def next_date(start_date, unit, count, occurrence_index):
    """Nth date in the rhythm, always measured from the start date.

    Measuring from the start rather than incrementing keeps a 31 January start
    on 28 February and then 31 March, instead of drifting to 28 March and
    staying there for the rest of the schedule.
    """
    start = getdate(start_date)
    count = max(1, int(count or 1))
    step = occurrence_index * count

    if unit in UNIT_DAYS:
        return add_days(start, step * UNIT_DAYS[unit])

    return add_months(start, step * UNIT_MONTHS.get(unit, 1))


MONTH_UNITS = ("Month", "Quarter", "Year")


def adjustment_applies(adjustment, unit):
    """End of month is meaningless on a daily or weekly rhythm.

    Forcing every date in August onto the thirty-first collapses thirty-one
    distinct postings into one date, which destroys the period boundaries. The
    working day rules are safe on any rhythm.
    """
    if adjustment in (None, "None"):
        return False
    if adjustment == "End of month":
        return unit in MONTH_UNITS
    return True


def apply_day_adjustment(date, adjustment, holiday_list=None, unit="Month"):
    date = getdate(date)

    if not adjustment_applies(adjustment, unit):
        return date

    if adjustment == "End of month":
        return get_last_day(date)

    if adjustment in ("Next working day", "Previous working day"):
        holidays = get_holidays(holiday_list)
        direction = 1 if adjustment == "Next working day" else -1
        guard = 0
        while date in holidays and guard < 30:
            date = add_days(date, direction)
            guard += 1

    return getdate(date)


def get_holidays(holiday_list):
    if not holiday_list:
        return set()
    rows = frappe.get_all(
        "Holiday",
        filters={"parent": holiday_list, "parenttype": "Holiday List"},
        pluck="holiday_date",
    )
    return {getdate(d) for d in rows}


def make_strictly_increasing(dates):
    """Guarantee unique, ascending posting dates.

    A day adjustment or a holiday rule can push two dates onto the same day.
    Two postings on one date break the period model and would breach the one
    entry per period idempotency key, so any collision is nudged forward.
    """
    out = []
    previous = None
    for date in dates:
        date = getdate(date)
        if previous is not None and date <= previous:
            date = add_days(previous, 1)
        out.append(date)
        previous = date
    return out


def describe_rhythm(count, unit, continue_count, continue_unit, until_date=None):
    """Plain sentence describing the schedule, shown live on the form."""
    count = max(1, int(count or 1))
    every = unit.lower() if count == 1 else "{0} {1}s".format(count, unit.lower())
    every = "every {0}".format(every)

    if continue_unit == "Until a date":
        span = "until {0}".format(until_date) if until_date else "until a date you choose"
    elif continue_unit == "Postings":
        n = int(continue_count or 0)
        span = "{0} time{1}".format(n, "" if n == 1 else "s")
    else:
        span = "for {0} {1}".format(int(continue_count or 0), continue_unit.lower())

    return "Posts {0}, {1}.".format(every, span)


# --------------------------------------------------------------- posting rule

POST_ON_RULES = {
    "End of each month":   {"unit": "Month",   "adjust": "End of month", "offset": 0},
    "Same day each month": {"unit": "Month",   "adjust": "None",         "offset": 1},
    "End of each quarter": {"unit": "Quarter", "adjust": "End of month", "offset": 0},
    "Every day":           {"unit": "Day",     "adjust": "None",         "offset": 0},
}


def posting_rule(post_on):
    return POST_ON_RULES.get(post_on or "End of each month",
                             POST_ON_RULES["End of each month"])


def posting_dates(start_date, post_on, term_end, limit=600):
    """Every posting date from the recurring start date to the end of the term.

    The user gives a start date and a duration. Which dates the entries land on
    is a posting rule, not a second date the user has to work out.

    Month end starts at the end of the month containing the start date, so a
    5 June start posts first on 30 June. Same day each month starts one month
    later, so the first entry covers a full month rather than a single day.
    """
    rule = posting_rule(post_on)
    start = getdate(start_date)
    term_end = getdate(term_end)

    dates = []
    for i in range(limit):
        raw = next_date(start, rule["unit"], 1, i + rule["offset"])
        date = apply_day_adjustment(raw, rule["adjust"], None, unit=rule["unit"])
        date = getdate(date)

        if date < start:
            continue
        if date > term_end:
            break

        dates.append(date)

    # The term nearly always ends between two posting dates. Without a closing
    # entry the tail of the period is never recognised and the schedule does not
    # sum to the total.
    if not dates:
        dates = [term_end]
    elif dates[-1] < term_end:
        dates.append(term_end)

    return make_strictly_increasing(dates)


def describe_plan(start_date, duration_value, duration_unit, until_date,
                  post_on, end_date, postings, amount=None):
    """One sentence covering the whole plan, shown live as the user types."""
    if duration_unit == "Until a date":
        span = _("until {0}").format(until_date) if until_date else _("until a date you choose")
    else:
        span = _("for {0} {1}").format(int(duration_value or 0), (duration_unit or "").lower())

    when = {
        "End of each month": _("at the end of each month"),
        "Same day each month": _("on the same day each month"),
        "End of each quarter": _("at the end of each quarter"),
        "Every day": _("every day"),
    }.get(post_on, _("at the end of each month"))

    text = _("Runs from {0} {1}, ending {2}. Posts {3}, {4} entries in total.").format(
        start_date, span, end_date, when, postings)

    return text
