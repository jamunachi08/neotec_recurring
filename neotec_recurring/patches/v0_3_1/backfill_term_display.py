"""Fill the visible term fields on templates saved before 0.3.1."""

import frappe


def execute():
    if not frappe.db.has_column("Recurring Entry Template", "ends_on"):
        return

    names = frappe.get_all("Recurring Entry Template", pluck="name")
    for name in names:
        try:
            doc = frappe.get_doc("Recurring Entry Template", name)
            doc.resolve_inputs()
            frappe.db.set_value(
                "Recurring Entry Template", name,
                {"ends_on": doc.ends_on, "ends_on_days": doc.ends_on_days},
                update_modified=False,
            )
        except Exception:
            continue

    frappe.db.commit()
