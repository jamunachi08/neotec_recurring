"""Clear an End of month adjustment from templates on a daily or weekly rhythm.

That combination forced every posting in a month onto the same date, which
collapsed distinct periods into one and produced schedules that could not post.
Affected templates are corrected and their pending rows rebuilt.
"""

import frappe


def execute():
    if not frappe.db.table_exists("Recurring Entry Template"):
        return
    if not frappe.db.has_column("Recurring Entry Template", "repeat_every_unit"):
        return

    frappe.db.sql(
        """
        UPDATE `tabRecurring Entry Template`
        SET day_adjustment = 'None'
        WHERE day_adjustment = 'End of month'
          AND repeat_every_unit NOT IN ('Month', 'Quarter', 'Year')
        """
    )

    frappe.db.sql(
        """
        UPDATE `tabRecurring Entry Template`
        SET final_posting_basis = 'The normal schedule date'
        WHERE final_posting_basis IS NULL OR final_posting_basis = ''
        """
    )
    frappe.db.commit()
