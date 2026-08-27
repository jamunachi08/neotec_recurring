app_name = "neotec_recurring"
app_title = "Neotec Recurring"
app_publisher = "Neotec Integrated Solution"
app_description = "Recurring Journal Entry engine for ERPNext"
app_email = "erpsupport@neotec.ai"
app_license = "Proprietary"
required_apps = ["erpnext"]

after_install = "neotec_recurring.setup.install.after_install"
after_migrate = "neotec_recurring.setup.install.after_migrate"

doc_events = {
    "Journal Entry": {
        "on_cancel": "neotec_recurring.events.journal_entry.on_cancel",
        "on_trash": "neotec_recurring.events.journal_entry.on_trash",
    },
    "Company": {
        "after_insert": "neotec_recurring.setup.install.on_company_insert",
    },
    "Accounting Dimension": {
        "after_insert": "neotec_recurring.events.accounting_dimension.after_change",
        "on_update": "neotec_recurring.events.accounting_dimension.after_change",
    },
}

scheduler_events = {
    "daily_long": [
        "neotec_recurring.tasks.post_due_entries",
    ]
}

app_include_js = "/assets/neotec_recurring/js/source_document.js"

# Setup is code driven in setup/install.py and re-asserted on every migrate.
# Deliberately empty: no fixture JSON is shipped or required.
fixtures = []
