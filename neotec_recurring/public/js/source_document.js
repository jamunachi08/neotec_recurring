// Adds a Create > Recurring Entry button to the accounting documents a
// prepayment usually originates from.
frappe.provide("neotec_recurring");

neotec_recurring.add_recurring_button = function (frm) {
    if (frm.doc.docstatus !== 1) return;
    if (!frappe.model.can_create("Recurring Entry Template")) return;

    frm.add_custom_button(__("Recurring Entry"), () => {
        frappe.call({
            method: "neotec_recurring.api.existing_templates_for",
            args: { doctype: frm.doctype, name: frm.doc.name }
        }).then(r => {
            const existing = r.message || [];
            if (!existing.length) return neotec_recurring.new_template(frm);

            frappe.confirm(
                __("{0} already has a recurring template ({1}). Create another?",
                   [frm.doc.name, existing.map(e => e.name).join(", ")]),
                () => neotec_recurring.new_template(frm)
            );
        });
    }, __("Create"));
};

neotec_recurring.new_template = function (frm) {
    frappe.call({
        method: "neotec_recurring.api.source_document_defaults",
        args: { doctype: frm.doctype, name: frm.doc.name },
        freeze: true
    }).then(r => {
        const v = r.message || {};
        frappe.new_doc("Recurring Entry Template", {}, doc => {
            Object.keys(v).forEach(k => {
                if (k.startsWith("suggested_")) return;
                if (v[k] !== null && v[k] !== undefined) doc[k] = v[k];
            });
            if (v.suggested_party) {
                frappe.show_alert({
                    message: __("{0} {1} carried over from the source. It applies only if the account accepts a party.",
                                [v.suggested_party_type, v.suggested_party]),
                    indicator: "blue"
                });
            }
        });
    });
};

["Sales Invoice", "Purchase Invoice", "Payment Entry", "Journal Entry", "Expense Claim"]
    .forEach(dt => {
        frappe.ui.form.on(dt, {
            refresh(frm) { neotec_recurring.add_recurring_button(frm); }
        });
    });
