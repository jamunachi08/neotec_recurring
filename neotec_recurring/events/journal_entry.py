"""Keep the schedule honest when a generated Journal Entry is cancelled or deleted."""

import frappe


def _reset_schedule_row(doc, status):
    if not doc.get("neotec_recurring_template"):
        return

    rows = frappe.get_all(
        "Recurring Entry Schedule",
        filters={
            "parent": doc.neotec_recurring_template,
            "parenttype": "Recurring Entry Template",
            "journal_entry": doc.name,
        },
        pluck="name",
    )

    for row in rows:
        frappe.db.set_value(
            "Recurring Entry Schedule",
            row,
            {"status": status, "journal_entry": None, "posted_on": None},
            update_modified=False,
        )


def on_cancel(doc, method=None):
    # Cancelled, not Pending. Re-posting is a deliberate act, not something the
    # scheduler should do on its own the next morning.
    _reset_schedule_row(doc, "Cancelled")


def on_trash(doc, method=None):
    _reset_schedule_row(doc, "Pending")
