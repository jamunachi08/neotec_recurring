import frappe

from neotec_recurring.setup.install import after_migrate


def execute():
    after_migrate()
