"""Set the Simple mode party visibility flags on existing templates."""

import frappe

from neotec_recurring.utils.party import PARTY_ACCOUNT_TYPES, get_account_type


def execute():
    if not frappe.db.has_column("Recurring Entry Template", "debit_takes_party"):
        return

    rows = frappe.get_all(
        "Recurring Entry Template",
        filters={"entry_mode": "Simple"},
        fields=["name", "debit_account", "credit_account"],
    )

    for row in rows:
        values = {}
        for side in ("debit", "credit"):
            account = row.get(side + "_account")
            takes = bool(account) and get_account_type(account) in PARTY_ACCOUNT_TYPES
            values[side + "_takes_party"] = 1 if takes else 0
        frappe.db.set_value("Recurring Entry Template", row.name, values,
                            update_modified=False)

    frappe.db.commit()
