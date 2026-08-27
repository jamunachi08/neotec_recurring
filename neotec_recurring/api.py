"""Whitelisted endpoints."""

import frappe
from frappe import _

from neotec_recurring.engine.runner import run_template


@frappe.whitelist()
def post_now(template, upto_date=None):
    """Post all due schedule rows for one template.

    Permission is checked against the template, and Journal Entry creation is
    checked separately so a user cannot post entries they could not create by
    hand.
    """
    doc = frappe.get_doc("Recurring Entry Template", template)
    doc.check_permission("write")

    if not frappe.has_permission("Journal Entry", "create"):
        frappe.throw(_("You are not permitted to create Journal Entries."))

    return run_template(doc, upto_date=upto_date, triggered_by="Manual")


@frappe.whitelist()
def plan_preview(start_date, duration_value=None, duration_unit=None, until_date=None,
                 post_on=None, day_count_convention=None, amount=None):
    """Derive the end date, posting dates and daily rate without saving.

    Called as the user types. Nothing is written.
    """
    from frappe.utils import add_days, add_months, cint, flt, fmt_money, formatdate, getdate

    from neotec_recurring.utils import daycount as dc
    from neotec_recurring.utils.schedule import describe_plan, posting_dates

    if not start_date:
        return {}

    convention = day_count_convention or dc.ACTUAL
    unit = duration_unit or "Months"
    n = cint(duration_value)
    start = getdate(start_date)

    try:
        if unit == "Until a date":
            if not until_date:
                return {"error": "no until date"}
            end = getdate(until_date)
        elif unit == "Days":
            end = dc.end_date_from_days(start, n, convention, True)
        elif unit == "Years":
            end = add_days(add_months(start, n * 12), -1)
        else:
            end = add_days(add_months(start, n), -1)

        if end < start:
            return {"error": "end before start"}

        dates = posting_dates(start, post_on, end)
    except Exception as exc:
        return {"error": frappe.utils.cstr(exc)}

    days = dc.days_inclusive(start, end, dc.ACTUAL)
    per_day = flt(flt(amount) / days, 4) if (amount and days) else 0

    headline = None
    if unit == "Days" and convention != dc.ACTUAL:
        if days != n:
            headline = _("A {0} day term under {1} spans {2} actual calendar days.").format(
                n, convention, days)

    return {
        "end_date": str(end),
        "first_posting_date": str(dates[0]) if dates else None,
        "postings": len(dates),
        "term_days": days,
        "amount_per_day": per_day,
        "sentence": describe_plan(formatdate(start), n, unit,
                                  formatdate(until_date) if until_date else None,
                                  post_on, formatdate(end), len(dates)),
        "headline": headline,
    }


@frappe.whitelist()
def preview_schedule_rows(doc):
    """Build the schedule for an unsaved document and return it for display.

    Nothing is written. Validation errors are returned as text rather than
    thrown, so the preview dialog can explain the problem instead of the user
    meeting a red error box.
    """
    import json

    if isinstance(doc, str):
        doc = json.loads(doc)

    template = frappe.get_doc(doc)
    template.flags.ignore_permissions = True

    try:
        template.resolve_inputs()
        rows = template.build_schedule(commit_to_doc=False)
    except frappe.ValidationError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": frappe.utils.cstr(e)}

    currency = frappe.get_cached_value("Company", template.company, "default_currency") \
        if template.company else None
    precision = template.amount_precision()

    total_days = sum(r["period_days"] for r in rows)

    # Running remainder, so the schedule can be checked the way an accountant
    # checks it: total term less each period until nothing is left.
    remaining = total_days
    out_rows = []
    for r in rows:
        remaining -= r["period_days"]
        out_rows.append({
            "schedule_date": str(r["schedule_date"]),
            "period_start": str(r["period_start"]),
            "period_end": str(r["period_end"]),
            "period_days": r["period_days"],
            "days_left": remaining,
            "amount": r["amount"],
            # Formatted here rather than in the browser, where the site float
            # precision was rendering a two decimal riyal amount as 66.0900.
            "amount_display": frappe.utils.fmt_money(
                r["amount"], precision=precision, currency=currency),
        })

    # The same schedule counted under the other family of conventions, so the
    # effect of the choice is visible side by side instead of on paper.
    from neotec_recurring.utils import daycount as dc

    alternative = (dc.EU_30E_360 if template.day_count_convention in dc.ACTUAL_FAMILY
                   else dc.ACTUAL)
    for r, row in zip(rows, out_rows):
        row["alt_days"] = dc.days_inclusive(
            r["period_start"], r["period_end"], alternative)

    alt_total = sum(r["alt_days"] for r in out_rows)

    return {
        "rows": out_rows,
        "convention": template.day_count_convention,
        "alt_convention": alternative,
        "alt_total_days": alt_total,
        "total_display": frappe.utils.fmt_money(
            sum(r["amount"] for r in rows), precision=precision, currency=currency),
        "total": sum(r["amount"] for r in rows),
        "total_days": total_days,
        "currency": currency,
        "sentence": template.schedule_summary,
    }


@frappe.whitelist()
def create_party_dimension(document_type):
    """Create an Accounting Dimension over Customer, Supplier or Employee.

    ERPNext adds the field to Journal Entry Account and GL Entry, and this app
    mirrors it onto the template and its lines immediately. That gives party
    traceability on accrued revenue, prepayments and expense accounts, none of
    which can carry a Party.

    Idempotent.
    """
    from neotec_recurring.utils.party import TRACKABLE_PARTY_TYPES, get_party_dimension

    if document_type not in TRACKABLE_PARTY_TYPES:
        frappe.throw(_("{0} is not a trackable party type.").format(document_type))

    if not frappe.has_permission("Accounting Dimension", "create"):
        frappe.throw(_("You are not permitted to create Accounting Dimensions."))

    existing = get_party_dimension(document_type)
    if existing:
        return {"created": False, "name": existing.name, "fieldname": existing.fieldname}

    doc = frappe.get_doc({"doctype": "Accounting Dimension", "document_type": document_type})
    doc.insert()
    frappe.db.commit()

    from neotec_recurring.setup.install import sync_dimension_fields

    sync_dimension_fields()
    frappe.db.commit()

    return {"created": True, "name": doc.name, "fieldname": doc.fieldname}


@frappe.whitelist()
def party_tracking_status(party_type):
    """Whether an Accounting Dimension over this party type is configured."""
    from neotec_recurring.utils.party import get_party_dimension

    dimension = get_party_dimension(party_type) if party_type else None
    return {
        "dimension": dimension.fieldname if dimension else None,
        "label": (dimension.label or dimension.fieldname) if dimension else None,
    }


@frappe.whitelist()
def create_employee_dimension():
    """Create an Accounting Dimension over Employee.

    ERPNext will add an employee field to Journal Entry Account, GL Entry and
    every other dimension-aware doctype, and this app mirrors it onto the
    template and its lines on the next save. That gives employee traceability on
    prepayments, insurance and expense accounts, which cannot carry a Party.

    Idempotent: returns the existing dimension if one is already configured.
    """
    from neotec_recurring.utils.party import get_employee_dimension

    if not frappe.has_permission("Accounting Dimension", "create"):
        frappe.throw(_("You are not permitted to create Accounting Dimensions."))

    existing = get_employee_dimension()
    if existing:
        return {"created": False, "name": existing.name, "fieldname": existing.fieldname}

    doc = frappe.get_doc({
        "doctype": "Accounting Dimension",
        "document_type": "Employee",
    })
    doc.insert()
    frappe.db.commit()

    # Mirror it onto the recurring doctypes straight away rather than waiting
    # for the next migrate.
    from neotec_recurring.setup.install import sync_dimension_fields

    sync_dimension_fields()
    frappe.db.commit()

    return {"created": True, "name": doc.name, "fieldname": doc.fieldname}


@frappe.whitelist()
def party_capability(account):
    """What a given account can carry: a party, and if so which types."""
    from neotec_recurring.utils.party import (
        PREFERRED_PARTY_TYPE,
        get_account_type,
        get_employee_dimension,
        get_valid_party_types,
    )

    account_type = get_account_type(account)
    takes_party = account_type in ("Receivable", "Payable")
    dimension = get_employee_dimension()

    return {
        "account_type": account_type,
        "takes_party": takes_party,
        "valid_party_types": get_valid_party_types(account_type) if takes_party else [],
        "default_party_type": PREFERRED_PARTY_TYPE.get(account_type) if takes_party else None,
        "employee_dimension": dimension.fieldname if dimension else None,
    }


@frappe.whitelist()
def employee_tracking_status():
    """Whether an Accounting Dimension over Employee is configured."""
    from neotec_recurring.utils.party import get_employee_dimension

    dimension = get_employee_dimension()
    return {
        "dimension": dimension.fieldname if dimension else None,
        "label": (dimension.label or dimension.fieldname) if dimension else None,
    }


@frappe.whitelist()
def source_document_defaults(doctype, name):
    """Values for a new template created from an accounting document."""
    from neotec_recurring.events.source_document import source_defaults

    if not frappe.has_permission("Recurring Entry Template", "create"):
        frappe.throw(_("You are not permitted to create Recurring Entry Templates."))

    return source_defaults(doctype, name)


@frappe.whitelist()
def existing_templates_for(doctype, name):
    """Templates already created from this document, so a second one is a choice."""
    return frappe.get_all(
        "Recurring Entry Template",
        filters={"source_doctype": doctype, "source_document": name, "docstatus": ["<", 2]},
        fields=["name", "title", "status", "amount"],
    )
