"""Mirror a new or changed Accounting Dimension onto the recurring doctypes.

Without this, a dimension added after installation would only appear on the
template after the next bench migrate. With it, the field is available as soon
as the dimension is saved, on every company, with no manual step.
"""

import frappe


def after_change(doc, method=None):
    if doc.get("disabled"):
        return

    try:
        from neotec_recurring.setup.install import sync_dimension_fields

        sync_dimension_fields()
        frappe.clear_cache(doctype="Recurring Entry Template")
        frappe.clear_cache(doctype="Recurring Entry Line")
    except Exception:
        frappe.log_error(
            title="Neotec Recurring dimension sync",
            message=frappe.get_traceback(),
        )
