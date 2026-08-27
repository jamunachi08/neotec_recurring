"""Create a Recurring Entry Template from an accounting document.

A prepayment nearly always starts life as a Purchase Invoice, a Payment Entry or
a Journal Entry. Retyping the company, the date, the amount and the accounts
onto a template is both slow and a chance to get them wrong, so the button
carries them across.
"""

import frappe
from frappe import _
from frappe.utils import flt

SUPPORTED = ("Sales Invoice", "Purchase Invoice", "Payment Entry",
             "Journal Entry", "Expense Claim")

DATE_FIELD = {
    "Sales Invoice": "posting_date",
    "Purchase Invoice": "posting_date",
    "Payment Entry": "posting_date",
    "Journal Entry": "posting_date",
    "Expense Claim": "posting_date",
}

AMOUNT_FIELD = {
    "Sales Invoice": "base_grand_total",
    "Purchase Invoice": "base_grand_total",
    "Payment Entry": "base_paid_amount",
    "Journal Entry": "total_debit",
    "Expense Claim": "total_sanctioned_amount",
}


def source_defaults(doctype, name):
    """Everything a template can usefully inherit from a source document."""
    if doctype not in SUPPORTED:
        frappe.throw(_("{0} is not supported as a recurring source.").format(doctype))

    doc = frappe.get_doc(doctype, name)
    doc.check_permission("read")

    posting_date = doc.get(DATE_FIELD.get(doctype, "posting_date"))
    amount = flt(doc.get(AMOUNT_FIELD.get(doctype)))

    values = {
        "source_doctype": doctype,
        "source_document": name,
        "main_entry_date": posting_date,
        "start_date": posting_date,
        "company": doc.get("company"),
        "amount": amount,
        "amount_type": "Total for the whole term",
        "split_by_days": 1,
        "title": _("{0} - {1}").format(doctype, name),
        "user_remark": _("Amortisation of {0} {1}").format(doctype, name),
    }

    # A party on the source is only meaningful where the template account can
    # hold one, so it is offered rather than forced.
    if doctype in ("Purchase Invoice",):
        values["credit_account"] = doc.get("credit_to")
        values["suggested_party_type"] = "Supplier"
        values["suggested_party"] = doc.get("supplier")
    elif doctype == "Sales Invoice":
        values["debit_account"] = doc.get("debit_to")
        values["suggested_party_type"] = "Customer"
        values["suggested_party"] = doc.get("customer")
    elif doctype == "Expense Claim":
        values["track_employee"] = 1
        values["for_employee"] = doc.get("employee")

    return values
