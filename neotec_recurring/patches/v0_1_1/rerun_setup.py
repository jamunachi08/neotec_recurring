"""Re-assert the full code driven setup for the 0.1.1 release.

Adds the workspace, seeds settings defaults and refreshes the dimension mirror
on sites installed at 0.1.0.
"""

import frappe

from neotec_recurring.setup.install import after_migrate


def execute():
    after_migrate()
    frappe.db.commit()
