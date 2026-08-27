"""Initialise the employee tracking flag on existing templates.

Nothing is switched on. Templates that already name an employee through a
dimension or a party keep working exactly as before.
"""

import frappe


def execute():
    if not frappe.db.has_column("Recurring Entry Template", "track_employee"):
        return

    frappe.db.sql(
        """
        UPDATE `tabRecurring Entry Template`
        SET track_employee = 0
        WHERE track_employee IS NULL
        """
    )
    frappe.db.commit()
