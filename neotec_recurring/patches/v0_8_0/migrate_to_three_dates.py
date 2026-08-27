"""Map 0.7.x templates onto the three date model.

Covers from and first posting date collapse into a single recurring start date,
the rhythm and term pair collapses into a duration, and the day adjustment
becomes a posting rule. Schedules are not rebuilt, so nothing already posted
moves.
"""

import frappe

POST_ON = {
    ("Month", "End of month"): "End of each month",
    ("Month", "None"): "Same day each month",
    ("Quarter", "End of month"): "End of each quarter",
    ("Quarter", "None"): "End of each quarter",
    ("Day", "None"): "Every day",
    ("Week", "None"): "Every day",
}

DURATION = {
    "Days": "Days",
    "Weeks": "Days",
    "Months": "Months",
    "Years": "Years",
    "Until a date": "Until a date",
    "Postings": "Months",
}


def execute():
    if not frappe.db.has_column("Recurring Entry Template", "duration_unit"):
        return

    rows = frappe.db.sql(
        "SELECT * FROM `tabRecurring Entry Template`", as_dict=True
    )

    for old in rows:
        values = {}

        # The recurring start date is where coverage began.
        values["start_date"] = old.get("covers_from") or old.get("start_date")
        if not values["start_date"]:
            continue

        unit = old.get("continue_for_unit") or "Postings"
        count = frappe.utils.cint(old.get("continue_for_count"))

        values["duration_unit"] = DURATION.get(unit, "Months")
        if unit == "Weeks":
            values["duration_value"] = count * 7
        elif unit == "Postings":
            # A posting count only equals a month count on a monthly rhythm,
            # which is what almost every existing template uses.
            multiplier = {"Month": 1, "Quarter": 3, "Year": 12}.get(
                old.get("repeat_every_unit"), 1)
            values["duration_value"] = count * multiplier * max(
                1, frappe.utils.cint(old.get("repeat_every_count")) or 1)
        else:
            values["duration_value"] = count

        values["post_on"] = POST_ON.get(
            (old.get("repeat_every_unit"), old.get("day_adjustment") or "None"),
            "End of each month")

        frappe.db.set_value("Recurring Entry Template", old.name, values,
                            update_modified=False)

    frappe.db.commit()
