"""Posting engine.

Every schedule row is posted inside its own savepoint so a single bad row cannot
poison the rest of the run, and the idempotency key is checked before any write.
"""

import frappe
from frappe import _
from frappe.utils import add_days, getdate, nowdate, today

from neotec_recurring.engine.builder import build_journal_entry


def _settings():
    return frappe.get_cached_doc("Recurring Entry Settings")


def existing_journal_entry(template_name, schedule_date, is_reversal=0):
    """Idempotency key: one non cancelled JE per template per period."""
    return frappe.db.exists(
        "Journal Entry",
        {
            "neotec_recurring_template": template_name,
            "neotec_recurring_schedule_date": getdate(schedule_date),
            "neotec_recurring_is_reversal": is_reversal,
            "docstatus": ["<", 2],
        },
    )


def is_period_closed(company, posting_date):
    """Return True when a Journal Entry cannot legitimately be posted on this date.

    Two independent mechanisms close a period in ERPNext and both are checked.
    Matching a Period Closing Voucher against the fiscal year that actually
    contains the date matters: without it, a voucher closing one year blocks
    every date in every other year for the same company.
    """
    posting_date = getdate(posting_date)

    if _blocked_by_accounting_period(company, posting_date):
        return True

    return _blocked_by_period_closing(company, posting_date)


def _blocked_by_accounting_period(company, posting_date):
    """Accounting Period with Journal Entry flagged closed in its child table."""
    periods = frappe.get_all(
        "Accounting Period",
        filters={
            "company": company,
            "start_date": ["<=", posting_date],
            "end_date": [">=", posting_date],
        },
        pluck="name",
    )

    for period in periods:
        if frappe.db.exists(
            "Closed Document",
            {
                "parent": period,
                "parenttype": "Accounting Period",
                "document_type": "Journal Entry",
                "closed": 1,
            },
        ):
            return True

    return False


def _blocked_by_period_closing(company, posting_date):
    """Period Closing Voucher for the fiscal year containing this date.

    A voucher closes the books up to and including its own posting date within
    its own fiscal year. A later date in the same year is still open, and a
    date in a different fiscal year is unaffected.
    """
    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        {
            "year_start_date": ["<=", posting_date],
            "year_end_date": [">=", posting_date],
        },
        "name",
    )

    if not fiscal_year:
        # Let ERPNext raise its own missing-fiscal-year error, which names the
        # date and is clearer than a generic closed-period message.
        return False

    return bool(
        frappe.db.exists(
            "Period Closing Voucher",
            {
                "company": company,
                "fiscal_year": fiscal_year,
                "docstatus": 1,
                "posting_date": [">=", posting_date],
            },
        )
    )


def run_all(triggered_by="Scheduler"):
    settings = _settings()
    cutoff = add_days(nowdate(), int(settings.post_ahead_days or 0))

    templates = frappe.get_all(
        "Recurring Entry Template",
        filters={"docstatus": 1, "status": "Active", "disabled": 0},
        pluck="name",
    )

    summary = {"posted": 0, "failed": 0, "skipped": 0}

    for name in templates:
        try:
            doc = frappe.get_doc("Recurring Entry Template", name)
            result = run_template(doc, upto_date=cutoff, triggered_by=triggered_by)
            for key in summary:
                summary[key] += result.get(key, 0)
        except Exception as exc:
            frappe.db.rollback()
            frappe.log_error(
                title="Recurring Entry template run failed",
                message="{0}\n{1}".format(name, frappe.get_traceback()),
            )
            summary["failed"] += 1

    return summary


def run_template(template, upto_date=None, triggered_by="Manual"):
    settings = _settings()
    upto_date = getdate(upto_date or today())
    floor_date = add_days(upto_date, -int(settings.max_backdate_days or 90))
    max_attempts = int(settings.max_attempts or 3)

    result = {"posted": 0, "failed": 0, "skipped": 0}

    for row in template.schedule:
        if row.status not in ("Pending", "Failed"):
            continue
        if getdate(row.schedule_date) > upto_date:
            continue
        if getdate(row.schedule_date) < getdate(floor_date):
            _mark(row, "Skipped", error=_("Older than the backdating limit."))
            result["skipped"] += 1
            continue
        if int(row.attempts or 0) >= max_attempts:
            result["skipped"] += 1
            continue

        existing = existing_journal_entry(template.name, row.schedule_date)
        if existing:
            _mark(row, "Posted", journal_entry=existing)
            result["skipped"] += 1
            continue

        if is_period_closed(template.company, row.schedule_date):
            _mark(row, "Failed", error=_("Accounting period is closed."), bump=True)
            result["failed"] += 1
            continue

        savepoint = "recurring_{0}".format(row.name.replace("-", "_")[:40])
        try:
            frappe.db.savepoint(savepoint)

            je = build_journal_entry(template, row)
            je.insert()
            if template.auto_submit:
                je.submit()

            _mark(row, "Posted" if template.auto_submit else "Pending", journal_entry=je.name)
            _log(template, row, "Success", je.name, triggered_by)
            frappe.db.commit()
            result["posted"] += 1

        except Exception:
            frappe.db.rollback(save_point=savepoint)
            message = frappe.get_traceback()
            _mark(row, "Failed", error=message[-500:], bump=True)
            _log(template, row, "Failed", None, triggered_by, message)
            frappe.db.commit()
            result["failed"] += 1

    _refresh_status(template)

    if result["failed"]:
        notify_failures(template, result)

    return result


def notify_failures(template, result):
    """Send a Notification Log entry to every user holding the notify role."""
    settings = _settings()
    if not settings.notify_on_failure or not settings.notify_role:
        return

    recipients = frappe.get_all(
        "Has Role",
        filters={"role": settings.notify_role, "parenttype": "User"},
        pluck="parent",
    )
    recipients = [
        u
        for u in set(recipients)
        if frappe.db.get_value("User", u, "enabled")
        and u not in ("Administrator", "Guest")
    ]

    if not recipients:
        return

    subject = _("Recurring Entry posting failed: {0}").format(template.title or template.name)
    message = _("{0} entries failed, {1} posted, {2} skipped. Open the Recurring Entry Log for detail.").format(
        result.get("failed", 0), result.get("posted", 0), result.get("skipped", 0)
    )

    for user in recipients:
        try:
            frappe.get_doc(
                {
                    "doctype": "Notification Log",
                    "for_user": user,
                    "type": "Alert",
                    "document_type": "Recurring Entry Template",
                    "document_name": template.name,
                    "subject": subject,
                    "email_content": message,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(
                title="Recurring Entry notification failed",
                message=frappe.get_traceback(),
            )


def _mark(row, status, journal_entry=None, error=None, bump=False):
    values = {"status": status, "last_error": error}
    if journal_entry:
        values["journal_entry"] = journal_entry
        values["posted_on"] = frappe.utils.now()
    if bump:
        values["attempts"] = int(row.attempts or 0) + 1
    frappe.db.set_value("Recurring Entry Schedule", row.name, values, update_modified=False)


def _log(template, row, status, journal_entry, triggered_by, message=None):
    frappe.get_doc(
        {
            "doctype": "Recurring Entry Log",
            "template": template.name,
            "schedule_date": row.schedule_date,
            "status": status,
            "journal_entry": journal_entry,
            "triggered_by": triggered_by,
            "message": message,
        }
    ).insert(ignore_permissions=True)


def _refresh_status(template):
    pending = frappe.db.count(
        "Recurring Entry Schedule",
        {"parent": template.name, "parenttype": "Recurring Entry Template", "status": ["in", ("Pending", "Failed")]},
    )
    if not pending and template.status == "Active":
        frappe.db.set_value("Recurring Entry Template", template.name, "status", "Completed")
        frappe.db.commit()
