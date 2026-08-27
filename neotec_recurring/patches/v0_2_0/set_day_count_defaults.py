"""Backfill the day count convention on templates created before 0.2.0.

Actual (Calendar Days) reproduces the previous behaviour exactly, so existing
schedules are unchanged. Period coverage columns are left blank on posted rows
and are filled the next time a template is saved.
"""

import frappe


def execute():
    if not frappe.db.has_column("Recurring Entry Template", "day_count_convention"):
        return

    frappe.db.sql(
        """
        UPDATE `tabRecurring Entry Template`
        SET day_count_convention = 'Actual (Calendar Days)'
        WHERE day_count_convention IS NULL OR day_count_convention = ''
        """
    )
    frappe.db.sql(
        """
        UPDATE `tabRecurring Entry Template`
        SET term_inclusive = 1
        WHERE term_inclusive IS NULL
        """
    )
    frappe.db.commit()
