"""Accounting Dimension helpers.

Dimensions are never hardcoded. Everything is read from the Accounting
Dimension and Accounting Dimension Detail doctypes so that any dimension the
client adds later is picked up automatically on the next migrate.
"""

import frappe


DEFAULT_DIMENSIONS = ("cost_center", "project")


def get_active_dimensions():
    """Return every enabled Accounting Dimension.

    Cost Center and Project are standard fields on Journal Entry Account and are
    handled separately, so they are excluded here.
    """
    rows = frappe.get_all(
        "Accounting Dimension",
        filters={"disabled": 0},
        fields=["name", "fieldname", "document_type", "label"],
        order_by="name asc",
    )
    return [r for r in rows if r.fieldname not in DEFAULT_DIMENSIONS]


def get_dimension_details(company):
    """Per company defaults and mandatory flags, keyed by dimension fieldname."""
    out = {}
    details = frappe.get_all(
        "Accounting Dimension Detail",
        filters={"company": company},
        fields=[
            "parent",
            "default_dimension",
            "mandatory_for_bs",
            "mandatory_for_pl",
        ],
    )
    fieldname_by_parent = {
        d.name: d.fieldname
        for d in frappe.get_all("Accounting Dimension", fields=["name", "fieldname"])
    }
    for d in details:
        fieldname = fieldname_by_parent.get(d.parent)
        if fieldname:
            out[fieldname] = d
    return out


def get_company_default_cost_center(company):
    """Company.cost_center is the main cost center created with the company.

    Using it as a last resort is what removes the need to set a cost center on
    every template on every company. ERPNext requires a cost center on Profit
    and Loss accounts, and this is the value ERPNext itself falls back to.
    """
    if not company:
        return None
    return frappe.get_cached_value("Company", company, "cost_center")


def resolve_dimension_values(template, line, company):
    """Line value, then template default, then company dimension default.

    Cost center has one further fallback: the company main cost center. Returns
    a dict ready to merge into a Journal Entry Account row.
    """
    values = {}
    details = get_dimension_details(company)

    for fieldname in DEFAULT_DIMENSIONS:
        value = line.get(fieldname) or template.get(fieldname)
        if not value and fieldname == "cost_center":
            value = get_company_default_cost_center(company)
        if value:
            values[fieldname] = value

    for dim in get_active_dimensions():
        fieldname = dim.fieldname
        value = line.get(fieldname) or template.get(fieldname)
        if not value:
            detail = details.get(fieldname)
            value = detail.default_dimension if detail else None
        if value:
            values[fieldname] = value

    return values


def validate_mandatory_dimensions(template, line, company, account):
    """Raise at template save time rather than at 3am in the scheduler.

    Covers two separate rules:

    1. ERPNext requires a cost center on every Profit and Loss account. This is
       built into GL Entry and is independent of any Accounting Dimension
       configuration, so it is checked unconditionally.

    2. Accounting Dimension Detail carries mandatory_for_pl and mandatory_for_bs
       per company. The correct flag is chosen from the account root type.
    """
    root_type = frappe.db.get_value("Account", account, "root_type")
    if not root_type:
        return []

    is_pl = root_type in ("Income", "Expense")
    details = get_dimension_details(company)
    resolved = resolve_dimension_values(template, line, company)
    missing = []

    if is_pl and not resolved.get("cost_center"):
        missing.append(
            "Cost Center (required by ERPNext on Profit and Loss accounts, and "
            "no company main cost center is set)"
        )

    for dim in get_active_dimensions():
        detail = details.get(dim.fieldname)
        if not detail:
            continue
        required = detail.mandatory_for_pl if is_pl else detail.mandatory_for_bs
        if required and not resolved.get(dim.fieldname):
            missing.append(dim.label or dim.fieldname)

    return missing
