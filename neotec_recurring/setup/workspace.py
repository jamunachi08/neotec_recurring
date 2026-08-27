"""Workspace creation, built in code so it self-heals on every migrate.

No fixture JSON. A workspace deleted or damaged on a client site is rebuilt by
the next bench migrate without anyone re-importing anything.
"""

import json

import frappe

WORKSPACE = "Neotec Recurring"
PARENT = "Accounting"

SHORTCUTS = [
    {"type": "DocType", "label": "Recurring Entry Template", "link_to": "Recurring Entry Template",
     "color": "Blue", "doc_view": "List"},
    {"type": "DocType", "label": "Recurring Entry Log", "link_to": "Recurring Entry Log",
     "color": "Grey", "doc_view": "List"},
    {"type": "DocType", "label": "Recurring Entry Settings", "link_to": "Recurring Entry Settings",
     "color": "Grey"},
]

LINKS = [
    {"type": "Card Break", "label": "Recurring Entries", "onboard": 0},
    {"type": "Link", "label": "Recurring Entry Template", "link_to": "Recurring Entry Template",
     "link_type": "DocType", "onboard": 1,
     "description": "Define a repeating journal entry and its schedule"},
    {"type": "Link", "label": "Recurring Entry Log", "link_to": "Recurring Entry Log",
     "link_type": "DocType", "onboard": 0,
     "description": "Every posting attempt, successful or otherwise"},

    {"type": "Card Break", "label": "Configuration", "onboard": 0},
    {"type": "Link", "label": "Recurring Entry Settings", "link_to": "Recurring Entry Settings",
     "link_type": "DocType", "onboard": 0,
     "description": "Scheduler, backdating and retry policy"},
    {"type": "Link", "label": "Accounting Dimension", "link_to": "Accounting Dimension",
     "link_type": "DocType", "onboard": 0,
     "description": "Dimensions are mirrored onto templates on migrate"},

    {"type": "Card Break", "label": "Related", "onboard": 0},
    {"type": "Link", "label": "Journal Entry", "link_to": "Journal Entry",
     "link_type": "DocType", "onboard": 0,
     "description": "Generated entries carry the Recurring Entry type"},
    {"type": "Link", "label": "Period Closing Voucher", "link_to": "Period Closing Voucher",
     "link_type": "DocType", "onboard": 0,
     "description": "Closed periods block recurring posting"},
]


def _content():
    return json.dumps([
        {"id": "hdr_shortcuts", "type": "header", "data": {
            "text": "<span class='h4'><b>Recurring Journal Entries</b></span>", "col": 12}},
        {"id": "sc_template", "type": "shortcut", "data": {
            "shortcut_name": "Recurring Entry Template", "col": 4}},
        {"id": "sc_log", "type": "shortcut", "data": {
            "shortcut_name": "Recurring Entry Log", "col": 4}},
        {"id": "sc_settings", "type": "shortcut", "data": {
            "shortcut_name": "Recurring Entry Settings", "col": 4}},
        {"id": "spacer_1", "type": "spacer", "data": {"col": 12}},
        {"id": "hdr_cards", "type": "header", "data": {
            "text": "<span class='h4'><b>Reports and Masters</b></span>", "col": 12}},
        {"id": "card_entries", "type": "card", "data": {
            "card_name": "Recurring Entries", "col": 4}},
        {"id": "card_config", "type": "card", "data": {
            "card_name": "Configuration", "col": 4}},
        {"id": "card_related", "type": "card", "data": {
            "card_name": "Related", "col": 4}},
    ])


def ensure_workspace():
    """Create or rebuild the workspace. Idempotent."""
    if frappe.db.exists("Workspace", WORKSPACE):
        doc = frappe.get_doc("Workspace", WORKSPACE)
        doc.set("links", [])
        doc.set("shortcuts", [])
    else:
        doc = frappe.new_doc("Workspace")
        doc.name = WORKSPACE

    doc.title = WORKSPACE
    doc.label = WORKSPACE
    doc.module = "Neotec Recurring"
    doc.icon = "accounting"
    doc.public = 1
    doc.is_hidden = 0
    doc.sequence_id = 22.0
    doc.content = _content()

    if frappe.db.exists("Workspace", PARENT):
        doc.parent_page = PARENT

    for s in SHORTCUTS:
        doc.append("shortcuts", s)

    for l in LINKS:
        doc.append("links", l)

    doc.flags.ignore_permissions = True
    doc.flags.ignore_links = True
    doc.save(ignore_permissions=True)

    return doc.name
