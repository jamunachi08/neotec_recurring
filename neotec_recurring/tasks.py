"""Scheduler entry points."""

import frappe

from neotec_recurring.engine.runner import run_all


def post_due_entries():
    """Daily scheduler hook. Enqueued on the long queue by scheduler_events."""
    if not frappe.db.get_single_value("Recurring Entry Settings", "enable_scheduler"):
        return
    run_all(triggered_by="Scheduler")
