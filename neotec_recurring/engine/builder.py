"""Journal Entry construction."""

import frappe
from frappe import _
from frappe.utils import flt

from neotec_recurring.setup.install import RECURRING_VOUCHER_TYPE
from neotec_recurring.utils.dimensions import resolve_dimension_values
from neotec_recurring.utils.party import (
    get_party_dimension,
    party_target,
    resolve_party,
)


def allocate_line_amounts(template, period_amount):
    """Split the period amount across template lines.

    Percentage lines take their share, Fixed lines take a literal amount, and
    Balancing lines absorb whatever is left. This is what makes multi line
    recurring entries possible instead of a hardcoded two line pair.
    """
    precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency") or 2
    amounts = {}

    debit_fixed = credit_fixed = 0.0
    balancing = {"Debit": [], "Credit": []}

    for line in template.lines:
        if line.allocation_type == "Fixed Amount":
            value = flt(line.fixed_amount, precision)
        elif line.allocation_type == "Percentage":
            value = flt(period_amount * flt(line.percentage) / 100.0, precision)
        else:
            balancing[line.entry_type].append(line)
            continue

        amounts[line.name] = value
        if line.entry_type == "Debit":
            debit_fixed += value
        else:
            credit_fixed += value

    for entry_type in ("Debit", "Credit"):
        rows = balancing[entry_type]
        if not rows:
            continue
        allocated = debit_fixed if entry_type == "Debit" else credit_fixed
        residual = flt(period_amount - allocated, precision)
        share = flt(residual / len(rows), precision)
        running = 0.0
        for idx, line in enumerate(rows):
            value = flt(residual - running, precision) if idx == len(rows) - 1 else share
            amounts[line.name] = value
            running = flt(running + value, precision)

    return amounts


def apply_tracked_party(template, line, row):
    """Attach the template party to one Journal Entry line.

    The destination depends on what the account can legally hold. A receivable
    account takes party_type Customer, a payable account takes Supplier or
    Employee, and anything else takes the Accounting Dimension over that
    doctype, because ERPNext rejects a party on an account that is neither
    receivable nor payable.

    An accrued revenue account with a blank account type is the common case:
    revenue is earned but not yet invoiced, so it is not a receivable and the
    customer belongs in the dimension.

    A value already set on the line always wins.
    """
    if not template.get("track_party"):
        return

    party_type = template.get("tracked_party_type")
    party = template.get("tracked_party")
    if not party_type or not party:
        return

    target = party_target(line.account, party_type)

    if target == "party":
        if not row.get("party"):
            row["party_type"] = party_type
            row["party"] = party
        return

    if target == "dimension":
        dimension = get_party_dimension(party_type)
        if dimension and not row.get(dimension.fieldname):
            row[dimension.fieldname] = party
        return

    title_field = {"Customer": "customer_name", "Supplier": "supplier_name",
                   "Employee": "employee_name"}.get(party_type)
    name = frappe.get_cached_value(party_type, party, title_field) if title_field else None
    note = _("{0}: {1} ({2})").format(party_type, name or party, party)
    row["user_remark"] = "{0} | {1}".format(row["user_remark"], note) if row.get("user_remark") else note


def build_journal_entry(template, schedule_row, is_reversal=False):
    """Return an unsaved Journal Entry for one schedule row."""
    precision = frappe.get_precision("Journal Entry Account", "debit_in_account_currency") or 2

    je = frappe.new_doc("Journal Entry")
    je.company = template.company
    je.posting_date = schedule_row.schedule_date
    je.voucher_type = template.voucher_type or RECURRING_VOUCHER_TYPE
    je.user_remark = template.user_remark or template.title
    je.neotec_recurring_template = template.name
    je.neotec_recurring_schedule_date = schedule_row.schedule_date
    je.neotec_recurring_is_reversal = 1 if is_reversal else 0

    if template.je_naming_series:
        je.naming_series = template.je_naming_series

    amounts = allocate_line_amounts(template, flt(schedule_row.amount, precision))

    for line in template.lines:
        amount = flt(amounts.get(line.name), precision)
        if not amount:
            continue

        entry_type = line.entry_type
        if is_reversal:
            entry_type = "Credit" if entry_type == "Debit" else "Debit"

        row = {
            "account": line.account,
            "user_remark": line.user_remark or template.user_remark,
        }

        if entry_type == "Debit":
            row["debit_in_account_currency"] = amount
        else:
            row["credit_in_account_currency"] = amount

        # Customer, Supplier and Employee are all copied through here. Which
        # ones are valid is decided by the account type, not by this code.
        party_type, party = resolve_party(line, line.account)
        if party_type and party:
            row["party_type"] = party_type
            row["party"] = party

        row.update(resolve_dimension_values(template, line, template.company))

        apply_tracked_party(template, line, row)

        je.append("accounts", row)

    if not je.accounts:
        frappe.throw(_("No Journal Entry lines were produced for {0}.").format(schedule_row.schedule_date))

    return je
