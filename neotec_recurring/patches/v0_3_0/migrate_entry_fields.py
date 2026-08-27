"""Map 0.2.x templates onto the plain language fields introduced in 0.3.0.

Frequency and interval become Post every, the end condition becomes Continue
for, and the amount mode becomes Amount type with a single amount field.
Schedules are not rebuilt, so nothing already posted moves.
"""

import frappe

FREQ_TO_UNIT = {
    "Daily": ("Day", 1),
    "Weekly": ("Week", 1),
    "Fortnightly": ("Week", 2),
    "Monthly": ("Month", 1),
    "Quarterly": ("Quarter", 1),
    "Half-Yearly": ("Quarter", 2),
    "Yearly": ("Year", 1),
    "Custom Days": ("Day", 1),
}

AMOUNT_MAP = {
    "Fixed Per Period": ("Per posting", "amount_per_period", 0),
    "Total Split Equally": ("Total for the whole term", "total_amount", 0),
    "Total Split by Days": ("Total for the whole term", "total_amount", 1),
    "Daily Rate": ("Per day", "daily_rate", 0),
    "Annual Amount": ("Per year", "annual_amount", 0),
}


def execute():
    table = "tabRecurring Entry Template"
    if not frappe.db.table_exists("Recurring Entry Template"):
        return
    if not frappe.db.has_column("Recurring Entry Template", "repeat_every_unit"):
        return

    rows = frappe.db.sql(
        "SELECT name FROM `{0}`".format(table), as_dict=True
    )

    for row in rows:
        old = frappe.db.sql(
            "SELECT * FROM `{0}` WHERE name=%s".format(table), row.name, as_dict=True
        )[0]

        values = {}

        unit, mult = FREQ_TO_UNIT.get(old.get("frequency") or "Monthly", ("Month", 1))
        values["repeat_every_unit"] = unit
        values["repeat_every_count"] = max(1, int(old.get("interval") or 1)) * mult

        end_condition = old.get("end_condition")
        if end_condition == "After Number of Occurrences":
            values["continue_for_unit"] = "Postings"
            values["continue_for_count"] = old.get("number_of_occurrences") or 1
        elif end_condition == "After Number of Days":
            values["continue_for_unit"] = "Days"
            values["continue_for_count"] = old.get("number_of_days") or 1
        elif end_condition == "On End Date":
            values["continue_for_unit"] = "Until a date"
            values["until_date"] = old.get("end_date")
        else:
            values["continue_for_unit"] = "Postings"
            values["continue_for_count"] = len(
                frappe.get_all("Recurring Entry Schedule",
                               filters={"parent": row.name,
                                        "parenttype": "Recurring Entry Template"})
            ) or 12

        amount_type, source_field, split = AMOUNT_MAP.get(
            old.get("amount_mode") or "Fixed Per Period", ("Per posting", "amount_per_period", 0)
        )
        values["amount_type"] = amount_type
        values["amount"] = old.get(source_field) or 0
        values["split_by_days"] = split

        lines = frappe.get_all(
            "Recurring Entry Line",
            filters={"parent": row.name, "parenttype": "Recurring Entry Template"},
            fields=["account", "entry_type", "allocation_type", "party", "party_type"],
            order_by="idx",
        )
        simple = (
            len(lines) == 2
            and all(l.allocation_type == "Balancing" for l in lines)
            and {l.entry_type for l in lines} == {"Debit", "Credit"}
        )
        if simple:
            values["entry_mode"] = "Simple"
            for l in lines:
                side = "debit" if l.entry_type == "Debit" else "credit"
                values[side + "_account"] = l.account
                values[side + "_party"] = l.party
                values[side + "_party_type"] = l.party_type
        else:
            values["entry_mode"] = "Advanced"

        frappe.db.set_value("Recurring Entry Template", row.name, values,
                            update_modified=False)

    frappe.db.commit()
