"""Set the period basis on templates created before 0.4.0.

Existing templates used a period that started on the posting date, so they are
set to that basis. Their schedules are unchanged. New templates default to the
in arrears basis, which is what an accrual or an amortisation needs.
"""

import frappe


def execute():
    if not frappe.db.has_column("Recurring Entry Template", "period_basis"):
        return

    frappe.db.sql(
        """
        UPDATE `tabRecurring Entry Template`
        SET period_basis = 'The period starting on the posting date'
        WHERE period_basis IS NULL OR period_basis = ''
        """
    )
    frappe.db.commit()
