"""Recurring Entry Template.

The form asks a clerk four questions: what it is for, when it repeats, how much,
and which two accounts. Everything the posting engine needs is derived from those
answers in resolve_inputs(), which runs first on every validate.

Design rule kept from earlier versions: every failure that can be detected from
the template is raised on save. The scheduler should only fail on conditions that
did not exist at save time, such as a period closed after the fact.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, cint, flt, getdate, today

from neotec_recurring.utils import daycount as dc
from neotec_recurring.utils.dimensions import validate_mandatory_dimensions
from neotec_recurring.utils.party import (
    PARTY_ACCOUNT_TYPES,
    get_account_type,
    get_party_dimension,
    party_alternative_hint,
    party_target,
    resolve_party_type,
)
from neotec_recurring.utils.schedule import (
    describe_plan,
    posting_dates,
)

MAX_OCCURRENCES = 600


class RecurringEntryTemplate(Document):

    # ------------------------------------------------------------------ flow

    def validate(self):
        self.resolve_inputs()
        self.build_lines_from_simple_entry()
        self.validate_company_accounts()
        self.validate_voucher_type()
        self.validate_lines()
        self.validate_party_configuration()
        self.validate_dimensions()
        self.validate_tracked_party()

        self.build_schedule()
        self.validate_schedule_size()
        self.validate_balanced()

    def on_submit(self):
        self.db_set("status", "Active")

    def on_cancel(self):
        posted = [r for r in self.schedule if r.status == "Posted"]
        if posted:
            frappe.throw(
                _("Cannot cancel: {0} schedule rows already have posted Journal Entries. "
                  "Cancel those entries first, or set the template to Paused instead.").format(len(posted))
            )
        self.db_set("status", "Cancelled")

    # -------------------------------------------------------------- defaults

    def resolve_inputs(self):
        """Fill in everything the user did not have to type.

        The user gives three things: when it starts, how long it runs, and how
        much. The end date, the posting dates and the per day rate are all
        derived from those.
        """
        self.duration_unit = self.duration_unit or "Months"
        self.post_on = self.post_on or "End of each month"
        self.day_count_convention = self.day_count_convention or dc.ACTUAL
        self.amount_type = self.amount_type or "Total for the whole term"
        self.entry_mode = self.entry_mode or "Simple"
        self.period_basis = self.period_basis or "The period ending on the posting date"
        self.final_posting_basis = self.final_posting_basis or "The normal schedule date"
        self.voucher_type = self.voucher_type or "Recurring Entry"

        if not self.start_date:
            frappe.throw(_("Please enter the recurring start date."))

        if self.duration_unit == "Until a date":
            if not self.until_date:
                frappe.throw(_("Please enter the date this runs until."))
            if getdate(self.until_date) < getdate(self.start_date):
                frappe.throw(_("The until date cannot be before the recurring start date."))
        elif cint(self.duration_value) < 1:
            frappe.throw(_("Please enter how long this runs for."))

        if flt(self.amount) <= 0:
            frappe.throw(_("Please enter an amount greater than zero."))

        if self.main_entry_date and getdate(self.main_entry_date) > getdate(self.start_date):
            frappe.msgprint(
                _("The main entry date is after the recurring start date. "
                  "Check that this is intended."),
                indicator="orange", alert=True)

        # Everything below is derived and shown read only.
        self.ends_on = self.term_end()
        self.term_days_actual = dc.days_inclusive(self.start_date, self.ends_on, dc.ACTUAL)

        if self.term_days_actual:
            self.amount_per_day = flt(
                flt(self.amount) / self.term_days_actual, self.amount_precision())

    def in_arrears(self):
        return self.period_basis != "The period starting on the posting date"

    def amount_precision(self):
        """Decimals for money on this template, from the company currency.

        Resolved here rather than guessed, so a three decimal Gulf currency is
        handled and a schedule previewed on an unsaved document rounds the same
        way as a saved one.
        """
        currency = None
        if self.company:
            currency = frappe.get_cached_value("Company", self.company, "default_currency")

        if currency:
            fraction = frappe.db.get_value(
                "Currency", currency, "smallest_currency_fraction_value")
            if fraction:
                text = str(flt(fraction))
                if "." in text:
                    return len(text.split(".")[1].rstrip("0")) or 2

        return cint(frappe.db.get_default("currency_precision")) or 2

    def coverage_start(self):
        """The day the service period begins. This is the recurring start date."""
        return getdate(self.start_date)

    def build_lines_from_simple_entry(self):
        """Turn a debit account and a credit account into the lines table.

        A clerk entering the common case never opens the grid. Advanced mode
        leaves whatever they built there untouched.
        """
        if self.entry_mode != "Simple":
            return

        if not self.debit_account or not self.credit_account:
            frappe.throw(_("Please choose both a debit and a credit account."))

        if self.debit_account == self.credit_account:
            frappe.throw(_("The debit and credit accounts cannot be the same."))

        self.set("lines", [])

        for account, side, party, chosen_type, flag in (
            (self.debit_account, "Debit", self.debit_party,
             self.debit_party_type, "debit_takes_party"),
            (self.credit_account, "Credit", self.credit_party,
             self.credit_party_type, "credit_takes_party"),
        ):
            account_type = get_account_type(account)
            takes_party = account_type in PARTY_ACCOUNT_TYPES
            self.set(flag, 1 if takes_party else 0)

            row = self.append("lines", {
                "account": account,
                "entry_type": side,
                "allocation_type": "Balancing",
                "party": party if takes_party else None,
            })

            if takes_party:
                # An explicit choice wins, so Employee can be used on a payable
                # account instead of the Supplier default.
                row.party_type = resolve_party_type(account_type, chosen_type)
            else:
                row.party_type = None

    # ------------------------------------------------------------- validation

    def validate_company_accounts(self):
        for line in self.lines:
            company = frappe.get_cached_value("Account", line.account, "company")
            if company != self.company:
                frappe.throw(
                    _("Row {0}: {1} belongs to {2}, not {3}.").format(
                        line.idx, line.account, company, self.company))
            if frappe.get_cached_value("Account", line.account, "is_group"):
                frappe.throw(_("Row {0}: {1} is a heading, not a postable account.").format(
                    line.idx, line.account))

    def validate_voucher_type(self):
        field = frappe.get_meta("Journal Entry").get_field("voucher_type")
        options = [o.strip() for o in (field.options or "").split("\n") if o.strip()]
        if self.voucher_type not in options:
            frappe.throw(_("{0} is not a valid Journal Entry type. Available: {1}").format(
                self.voucher_type, ", ".join(options)))

    def validate_lines(self):
        if len(self.lines) < 2:
            frappe.throw(_("A journal entry needs at least one debit and one credit line."))

        if {l.entry_type for l in self.lines} != {"Debit", "Credit"}:
            frappe.throw(_("There must be at least one Debit line and one Credit line."))

        for side in ("Debit", "Credit"):
            if not [l for l in self.lines
                    if l.entry_type == side and l.allocation_type == "Balancing"]:
                frappe.throw(
                    _("The {0} side needs at least one Balancing line to absorb rounding.").format(side))

        for line in self.lines:
            if line.allocation_type == "Percentage" and flt(line.percentage) <= 0:
                frappe.throw(_("Row {0}: percentage must be greater than zero.").format(line.idx))
            if line.allocation_type == "Fixed Amount" and flt(line.fixed_amount) <= 0:
                frappe.throw(_("Row {0}: fixed amount must be greater than zero.").format(line.idx))

    def validate_party_configuration(self):
        for line in self.lines:
            account_type = get_account_type(line.account)

            if account_type not in PARTY_ACCOUNT_TYPES:
                if line.party_type or line.party:
                    frappe.throw(
                        _("Row {0}: {1}").format(
                            line.idx, party_alternative_hint(line.account, account_type)))
                continue

            resolved = resolve_party_type(account_type, line.party_type)
            if not resolved:
                frappe.throw(_("Row {0}: no party type is configured for {1} accounts.").format(
                    line.idx, account_type))

            line.party_type = resolved

            if not line.party:
                frappe.throw(
                    _("Row {0}: {1} is a {2} account, so please choose a {3}.").format(
                        line.idx, line.account, account_type, resolved.lower()))

    def validate_tracked_party(self):
        """Work out where the party will land on each line, and say so.

        The routing note is written back to a read only field so the outcome is
        visible before saving rather than being discovered in the ledger.
        """
        if not cint(self.track_party):
            self.party_routing_note = None
            return

        if not self.tracked_party_type or not self.tracked_party:
            frappe.throw(
                _("Please choose the party type and the party, or untick "
                  "'Track a party on every line'."))

        if not frappe.db.exists(self.tracked_party_type, self.tracked_party):
            frappe.throw(_("{0} {1} does not exist.").format(
                self.tracked_party_type, self.tracked_party))

        by_target = {"party": [], "dimension": [], "remark": []}
        for line in self.lines:
            by_target[party_target(line.account, self.tracked_party_type)].append(line.account)

        dimension = get_party_dimension(self.tracked_party_type)
        parts = []

        if by_target["party"]:
            parts.append(_("{0} line(s) will carry Party Type {1}.").format(
                len(by_target["party"]), self.tracked_party_type))

        if by_target["dimension"]:
            parts.append(
                _("{0} line(s) will carry the {1} dimension, because those accounts "
                  "are not receivable or payable and ERPNext does not allow a Party "
                  "on them.").format(
                    len(by_target["dimension"]), dimension.label or dimension.fieldname))

        if by_target["remark"]:
            parts.append(
                _("{0} line(s) can only record the name in the narration. Create an "
                  "Accounting Dimension over {1} to post it to the ledger.").format(
                    len(by_target["remark"]), self.tracked_party_type))

        self.party_routing_note = " ".join(parts)

    def validate_dimensions(self):
        for line in self.lines:
            missing = validate_mandatory_dimensions(self, line, self.company, line.account)
            if missing:
                frappe.throw(
                    _("Row {0}: {1} is required for {2}. Set it on the line, in the "
                      "Cost Center and Dimensions section, or as the company main "
                      "cost center.").format(line.idx, ", ".join(missing), line.account))

    def validate_schedule_size(self):
        """Stop a schedule that is far larger than the user probably intended.

        The commonest mistake is entering a term in the rhythm box: Post every
        1 Day, continue for 174 Postings, when what was meant was a 174 day term
        posted monthly. Both are legitimate configurations, so this asks rather
        than refuses, and names the exact correction when the pattern matches.
        """
        threshold = cint(
            frappe.db.get_single_value("Recurring Entry Settings", "large_schedule_threshold")
        ) or 40

        count = cint(self.occurrences_display)
        if count <= threshold or cint(self.confirm_large_schedule):
            return

        message = _("This will create {0} journal entries.").format(count)

        if self.post_on == "Every day":
            message += " " + _(
                "If you meant monthly entries over this term, set Post entries on to "
                "End of each month in the Options section.")
        else:
            message += " " + _("Check the duration.")

        message += " " + _(
            "If this is correct, tick 'Yes, create this many entries' and save again."
        )

        frappe.throw(message, title=_("That is a lot of entries"))

    def validate_balanced(self):
        from neotec_recurring.engine.builder import allocate_line_amounts

        if not self.schedule:
            return

        amounts = allocate_line_amounts(self, flt(self.schedule[0].amount))
        debit = sum(flt(amounts.get(l.name)) for l in self.lines if l.entry_type == "Debit")
        credit = sum(flt(amounts.get(l.name)) for l in self.lines if l.entry_type == "Credit")

        if flt(debit, 2) != flt(credit, 2):
            frappe.throw(_("The lines do not balance. Debit {0} against credit {1}.").format(
                debit, credit))

    # ---------------------------------------------------------------- term

    def term_end(self):
        """Recurring end date, calculated from the start date and the duration."""
        start = getdate(self.start_date)
        unit = self.duration_unit
        n = cint(self.duration_value)

        if unit == "Until a date":
            return getdate(self.until_date)

        if unit == "Days":
            return dc.end_date_from_days(start, n, self.day_count_convention, True)

        if unit == "Years":
            return add_days(add_months(start, n * 12), -1)

        return add_days(add_months(start, n), -1)

    def schedule_dates(self):
        return posting_dates(self.start_date, self.post_on, self.term_end())

    def period_amounts(self, periods, bounds):
        precision = self.amount_precision()
        value = flt(self.amount)

        if self.amount_type == "Per posting":
            return [flt(value, precision)] * periods

        if self.amount_type == "Per day":
            return [flt(value * b[2], precision) for b in bounds]

        if self.amount_type == "Per year":
            return [
                flt(value * b[2] / dc.year_length(self.day_count_convention, b[0]), precision)
                for b in bounds
            ]

        # Total for the whole term
        if cint(self.split_by_days):
            total_days = sum(b[2] for b in bounds) or 1
            amounts = [flt(value * b[2] / total_days, precision) for b in bounds]
        else:
            share = flt(value / periods, precision)
            amounts = [share] * periods

        # The rounding residual lands on the last period so the schedule sums to
        # the total exactly. Without this a 12,000 total over 174 days leaves a
        # few halalas unallocated.
        residual = flt(value - sum(amounts), precision)
        if residual:
            amounts[-1] = flt(amounts[-1] + residual, precision)

        return amounts

    # ------------------------------------------------------------- schedule

    def build_schedule(self, commit_to_doc=True):
        """Regenerate pending rows only. Posted rows are never touched."""
        term_end = getdate(self.term_end())
        dates = self.schedule_dates()
        periods = len(dates)

        bounds = dc.period_bounds(
            dates, term_end, self.day_count_convention,
            coverage_start=self.coverage_start(),
            in_arrears=self.in_arrears(),
        )
        amounts = self.period_amounts(periods, bounds)

        locked = {
            getdate(r.schedule_date): r
            for r in (self.schedule or [])
            if r.status in ("Posted", "Cancelled", "Skipped")
        }

        rows = []
        for i, date in enumerate(dates):
            existing = locked.get(getdate(date))
            start, end, days = bounds[i]
            rows.append({
                "schedule_date": date,
                "period_start": start,
                "period_end": end,
                "period_days": days,
                "amount": existing.amount if existing else amounts[i],
                "status": existing.status if existing else "Pending",
                "journal_entry": existing.journal_entry if existing else None,
                "attempts": existing.attempts if existing else 0,
                "posted_on": existing.posted_on if existing else None,
            })

        precision = self.amount_precision()
        self.schedule_total = flt(sum(r["amount"] for r in rows), precision)
        self.schedule_total_days = sum(r["period_days"] for r in rows)
        self.number_of_postings = periods
        self.occurrences_display = periods
        self.first_posting_date = dates[0] if dates else None
        self.first_period_days = bounds[0][2] if bounds else 0

        self.schedule_summary = describe_plan(
            frappe.utils.formatdate(self.start_date),
            self.duration_value, self.duration_unit,
            frappe.utils.formatdate(self.until_date) if self.until_date else None,
            self.post_on, frappe.utils.formatdate(term_end), periods)

        if not commit_to_doc:
            return rows

        self.set("schedule", [])
        for row in rows:
            self.append("schedule", row)

        return rows
