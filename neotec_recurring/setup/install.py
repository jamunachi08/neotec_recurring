"""Code driven setup. No fixture JSON anywhere in this app.

Every function is idempotent and re-asserted on after_migrate, so a site is
self healing: a deleted workspace, a dimension added last week, a company
created this morning and a property setter wiped by an upgrade are all put back
by the next bench migrate. Nothing needs to be repeated per company or per
client site beyond installing the app.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter

from neotec_recurring.setup.workspace import ensure_workspace
from neotec_recurring.utils.dimensions import get_active_dimensions

RECURRING_VOUCHER_TYPE = "Recurring Entry"

SETTINGS_DEFAULTS = {
    "enable_scheduler": 1,
    "post_ahead_days": 0,
    "max_backdate_days": 90,
    "max_attempts": 3,
    "notify_on_failure": 1,
    "notify_role": "Accounts Manager",
}


def after_install():
    after_migrate()


def after_migrate():
    ensure_voucher_type()
    ensure_journal_entry_tracking_fields()
    sync_dimension_fields()
    ensure_settings()
    ensure_workspace()
    frappe.db.commit()


# --------------------------------------------------------------------- voucher

def ensure_voucher_type(value=RECURRING_VOUCHER_TYPE):
    """Append the option to Journal Entry.voucher_type if the exact string is absent.

    Applied as a Property Setter so it survives bench migrate. If the option is
    already present with the same spelling this is a no-op and any existing
    customisation is left untouched.
    """
    field = frappe.get_meta("Journal Entry").get_field("voucher_type")
    if not field:
        return False

    options = [o.strip() for o in (field.options or "").split("\n")]

    if value in options:
        return False

    options.append(value)
    make_property_setter(
        "Journal Entry",
        "voucher_type",
        "options",
        "\n".join([o for o in options if o is not None]),
        "Text",
        validate_fields_for_doctype=False,
    )
    frappe.clear_cache(doctype="Journal Entry")
    return True


# ------------------------------------------------------------- tracking fields

def ensure_journal_entry_tracking_fields():
    """Link every generated Journal Entry back to its template and period.

    The pair (template, schedule date) is the idempotency key that prevents
    double posting when a run is retried or a manual post overlaps the scheduler.
    """
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    create_custom_fields(
        {
            "Journal Entry": [
                {
                    "fieldname": "neotec_recurring_section",
                    "label": "Recurring",
                    "fieldtype": "Section Break",
                    "insert_after": "user_remark",
                    "collapsible": 1,
                    "depends_on": "neotec_recurring_template",
                },
                {
                    "fieldname": "neotec_recurring_template",
                    "label": "Recurring Entry Template",
                    "fieldtype": "Link",
                    "options": "Recurring Entry Template",
                    "insert_after": "neotec_recurring_section",
                    "read_only": 1,
                    "no_copy": 1,
                    "search_index": 1,
                    "print_hide": 1,
                },
                {
                    "fieldname": "neotec_recurring_schedule_date",
                    "label": "Recurring Schedule Date",
                    "fieldtype": "Date",
                    "insert_after": "neotec_recurring_template",
                    "read_only": 1,
                    "no_copy": 1,
                    "search_index": 1,
                    "print_hide": 1,
                },
                {
                    "fieldname": "neotec_recurring_is_reversal",
                    "label": "Is Recurring Reversal",
                    "fieldtype": "Check",
                    "insert_after": "neotec_recurring_schedule_date",
                    "read_only": 1,
                    "no_copy": 1,
                    "print_hide": 1,
                },
            ]
        },
        ignore_validate=True,
    )


# ----------------------------------------------------------------- dimensions

def sync_dimension_fields():
    """Mirror every active Accounting Dimension onto the template and its lines.

    Runs on migrate, so a dimension added months from now is picked up without a
    code change and without per-company work.
    """
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    dimensions = get_active_dimensions()
    if not dimensions:
        return

    template_fields = []
    line_fields = []

    template_anchor = "project"
    line_anchor = "project"

    for dim in dimensions:
        common = {
            "fieldname": dim.fieldname,
            "label": dim.label or dim.fieldname,
            "fieldtype": "Link",
            "options": dim.document_type,
        }
        template_fields.append(dict(common, insert_after=template_anchor))
        line_fields.append(dict(common, insert_after=line_anchor, columns=1))
        template_anchor = dim.fieldname
        line_anchor = dim.fieldname

    create_custom_fields(
        {
            "Recurring Entry Template": template_fields,
            "Recurring Entry Line": line_fields,
        },
        ignore_validate=True,
    )


# ------------------------------------------------------------------- settings

def ensure_settings():
    """Seed the settings single so the app is usable straight after install.

    Only blank fields are populated. A value an administrator has deliberately
    changed is never overwritten on a later migrate.
    """
    doc = frappe.get_single("Recurring Entry Settings")
    changed = False

    for fieldname, default in SETTINGS_DEFAULTS.items():
        current = doc.get(fieldname)
        if current in (None, ""):
            if fieldname == "notify_role" and not frappe.db.exists("Role", default):
                continue
            doc.set(fieldname, default)
            changed = True

    if changed:
        doc.flags.ignore_permissions = True
        doc.save(ignore_permissions=True)

    return changed


# --------------------------------------------------------------- company hook

def on_company_insert(doc, method=None):
    """Called when a new Company is created.

    Nothing company specific is stored by this app. Cost centers, dimension
    defaults and closed periods are all read live at posting time, so a new
    company works immediately. The hook re-asserts the dimension mirror because
    creating a company can create dimensions that did not exist before.
    """
    try:
        sync_dimension_fields()
    except Exception:
        frappe.log_error(
            title="Neotec Recurring company setup",
            message=frappe.get_traceback(),
        )
