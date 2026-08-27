"""Seed the large schedule threshold."""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Recurring Entry Settings"):
        return
    if not frappe.db.get_single_value("Recurring Entry Settings", "large_schedule_threshold"):
        frappe.db.set_single_value("Recurring Entry Settings", "large_schedule_threshold", 40)
        frappe.db.commit()
