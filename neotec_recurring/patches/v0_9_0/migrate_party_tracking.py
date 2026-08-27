"""Carry employee tracking onto the general party fields."""

import frappe


def execute():
    if not frappe.db.has_column("Recurring Entry Template", "tracked_party_type"):
        return

    frappe.db.sql(
        """
        UPDATE `tabRecurring Entry Template`
        SET track_party = 1,
            tracked_party_type = 'Employee',
            tracked_party = for_employee
        WHERE track_employee = 1
          AND for_employee IS NOT NULL
          AND (tracked_party IS NULL OR tracked_party = '')
        """
    )
    frappe.db.commit()
