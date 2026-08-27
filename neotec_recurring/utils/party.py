"""Party resolution driven by Account.account_type and the Party Type doctype.

ERPNext requires party_type and party on Receivable and Payable accounts, and
rejects them on every other account type. The mapping between the two is data,
not code: Party Type carries an account_type field.
"""

import frappe
from frappe import _


PARTY_ACCOUNT_TYPES = ("Receivable", "Payable")

# Used only to pick a sensible default when several Party Types share an
# account_type. An explicit party_type on the line always wins.
PREFERRED_PARTY_TYPE = {
    "Receivable": "Customer",
    "Payable": "Supplier",
}


def get_account_type(account):
    return frappe.get_cached_value("Account", account, "account_type")


def get_valid_party_types(account_type):
    if account_type not in PARTY_ACCOUNT_TYPES:
        return []
    return frappe.get_all(
        "Party Type",
        filters={"account_type": account_type},
        pluck="name",
        order_by="name asc",
    )


def resolve_party_type(account_type, explicit_party_type=None):
    """Return the party type to use, or None if the account takes no party."""
    if account_type not in PARTY_ACCOUNT_TYPES:
        return None

    valid = get_valid_party_types(account_type)

    if explicit_party_type:
        if explicit_party_type not in valid:
            frappe.throw(
                _("Party Type {0} is not valid for a {1} account. Valid options: {2}").format(
                    explicit_party_type, account_type, ", ".join(valid) or _("none configured")
                )
            )
        return explicit_party_type

    preferred = PREFERRED_PARTY_TYPE.get(account_type)
    if preferred in valid:
        return preferred

    return valid[0] if valid else None


def resolve_party(line, account):
    """Return (party_type, party) for a template line.

    Returns (None, None) when the account is not Receivable or Payable, which is
    what stops ERPNext throwing "Party Type and Party is only applicable against
    Receivable / Payable account" on expense lines.
    """
    account_type = get_account_type(account)

    if account_type not in PARTY_ACCOUNT_TYPES:
        return None, None

    party_type = resolve_party_type(account_type, line.get("party_type"))
    party = line.get("party")

    if not party:
        frappe.throw(
            _("Row {0}: Account {1} is a {2} account, so a Party is required.").format(
                line.get("idx"), account, account_type
            )
        )

    if not frappe.db.exists(party_type, party):
        frappe.throw(
            _("Row {0}: {1} {2} does not exist.").format(line.get("idx"), party_type, party)
        )

    return party_type, party


# ---------------------------------------------------------------- dimensions

def get_party_dimension(document_type):
    """Return the Accounting Dimension over a doctype, if one is configured.

    An asset or expense account cannot carry a party. ERPNext restricts
    party_type and party to Receivable and Payable accounts because a party on a
    GL Entry means a subledger balance, and a prepaid Iqama or an insurance
    prepayment is not owed to the employee.

    An Accounting Dimension over Employee is the correct instrument. It posts to
    GL Entry, works on every account type, and is filterable in the standard
    reports.
    """
    return frappe.db.get_value(
        "Accounting Dimension",
        {"document_type": document_type, "disabled": 0},
        ["name", "fieldname", "label"],
        as_dict=True,
    )


def get_employee_dimension():
    return get_party_dimension("Employee")


def party_alternative_hint(account, account_type):
    """Guidance shown when a party is set on an account that cannot carry one."""
    dimension = get_employee_dimension()
    described = account_type or _("neither receivable nor payable")

    if dimension:
        return _(
            "{0} is {1}, so ERPNext does not allow a Party on it. Use the {2} "
            "field in the dimensions section instead. It posts to the ledger and "
            "works on any account type."
        ).format(account, described, dimension.label or dimension.fieldname)

    return _(
        "{0} is {1}, so ERPNext does not allow a Party on it. To track an "
        "employee against a prepayment or an expense, create an Accounting "
        "Dimension over Employee. The field then appears on every template and "
        "every line automatically."
    ).format(account, described)


EMPLOYEE_PARTY_TYPE = "Employee"

# Party types that can also exist as an Accounting Dimension. The dimension
# doctype and the party type share a name for all three.
TRACKABLE_PARTY_TYPES = ("Customer", "Supplier", "Employee")


def party_target(account, party_type):
    """Where a party of this type can legally be recorded against this account.

    Returns "party", "dimension" or "remark".

    ERPNext permits party_type and party only on receivable and payable
    accounts, because a party on a GL Entry means a subledger balance. An
    accrued revenue account with a blank account type is not a receivable, so a
    customer cannot be written as a party on it. An Accounting Dimension over
    Customer records the same information without inventing a balance and
    without pulling the accrual into AR ageing.
    """
    if party_type not in TRACKABLE_PARTY_TYPES:
        return "remark"

    account_type = get_account_type(account)

    if account_type in PARTY_ACCOUNT_TYPES:
        if party_type in get_valid_party_types(account_type):
            return "party"

    return "dimension" if get_party_dimension(party_type) else "remark"


def employee_target(account):
    """Where an employee can legally be recorded against this account.

    Returns one of:
        "party"     the account is receivable or payable and Employee is a valid
                    party type for it, so party_type and party are used
        "dimension" the account cannot carry a party, so the Accounting
                    Dimension over Employee is used instead
        "remark"    neither is available; the name goes in the narration only

    ERPNext refuses party_type and party on anything that is not receivable or
    payable, so writing the party unconditionally would produce a template that
    saves and then fails at submit.
    """
    return party_target(account, EMPLOYEE_PARTY_TYPE)
