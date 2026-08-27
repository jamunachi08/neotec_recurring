frappe.ui.form.on("Recurring Entry Template", {
    setup(frm) {
        frm.set_query("for_employee", () => ({
            filters: { company: frm.doc.company, status: "Active" }
        }));

        const account_filter = () => ({
            filters: { company: frm.doc.company, is_group: 0 }
        });
        frm.set_query("debit_account", account_filter);
        frm.set_query("credit_account", account_filter);
        frm.set_query("account", "lines", account_filter);
        frm.set_query("cost_center", () => ({
            filters: { company: frm.doc.company, is_group: 0 }
        }));
    },

    refresh(frm) {
        refresh_plan(frm);

        if (frm.doc.docstatus === 0) {
            frm.add_custom_button(__("Preview Schedule"), () => preview(frm))
               .addClass("btn-primary");
        }

        if (frm.doc.docstatus !== 1 || frm.doc.disabled) return;

        const pending = (frm.doc.schedule || []).filter(r => r.status === "Pending").length;
        const failed  = (frm.doc.schedule || []).filter(r => r.status === "Failed").length;

        if (failed) {
            frm.dashboard.set_headline_safe(
                __("{0} schedule rows failed. Use Troubleshoot to see why.", [failed]));
        }

        if (pending || failed) {
            frm.add_custom_button(__("Post Due Entries"), () => {
                frappe.confirm(__("Post all schedule rows dated on or before today?"), () => {
                    frappe.call({
                        method: "neotec_recurring.api.post_now",
                        args: { template: frm.doc.name },
                        freeze: true, freeze_message: __("Posting Journal Entries")
                    }).then(r => {
                        const m = r.message || {};
                        frappe.msgprint(__("Posted {0}, failed {1}, skipped {2}.",
                            [m.posted || 0, m.failed || 0, m.skipped || 0]));
                        frm.reload_doc();
                    });
                });
            }).addClass("btn-primary");
        }

        if (failed) {
            frm.add_custom_button(__("Diagnose"), () => {
                frappe.call({ method: "neotec_recurring.api.diagnose",
                              args: { template: frm.doc.name }, freeze: true })
                .then(r => {
                    const items = (r.message || [])
                        .map(m => `<li>${frappe.utils.escape_html(m)}</li>`).join("");
                    frappe.msgprint({ title: __("Why rows are not posting"),
                        message: `<ul style="padding-left:18px;margin:0">${items}</ul>`,
                        wide: true });
                });
            }, __("Troubleshoot"));

            frm.add_custom_button(__("Reset Failed Rows"), () => {
                frappe.confirm(__("Return failed rows to Pending?"), () => {
                    frappe.call({ method: "neotec_recurring.api.reset_rows",
                                  args: { template: frm.doc.name }, freeze: true })
                    .then(r => { frappe.msgprint(__("{0} rows reset.", [r.message || 0]));
                                 frm.reload_doc(); });
                });
            }, __("Troubleshoot"));
        }

        frm.add_custom_button(__("Pause"),  () => set_status(frm, "Paused"), __("Status"));
        frm.add_custom_button(__("Resume"), () => set_status(frm, "Active"), __("Status"));
    },

    company(frm) {
        frm.set_value("debit_account", null);
        frm.set_value("credit_account", null);
        frm.set_value("lines", []);
    },

    track_party(frm) {
        if (!frm.doc.track_party) return;
        if (frm.doc.tracked_party_type) check_party_dimension(frm);
    },

    tracked_party_type(frm) {
        frm.set_value("tracked_party", null);
        frm.set_value("tracked_party_name", null);
        if (frm.doc.track_party && frm.doc.tracked_party_type) check_party_dimension(frm);
    },

    tracked_party(frm) {
        if (!frm.doc.tracked_party || !frm.doc.tracked_party_type) return;
        const title = { Customer: "customer_name", Supplier: "supplier_name",
                        Employee: "employee_name" }[frm.doc.tracked_party_type];
        frappe.db.get_value(frm.doc.tracked_party_type, frm.doc.tracked_party, title)
            .then(r => frm.set_value("tracked_party_name", (r.message || {})[title] || ""));
    },

    entry_mode(frm) {
        if (frm.doc.entry_mode === "Advanced" && !(frm.doc.lines || []).length) {
            // Carry the simple entry across so nothing is retyped.
            [[frm.doc.debit_account, "Debit"], [frm.doc.credit_account, "Credit"]]
                .filter(([a]) => a)
                .forEach(([account, side]) => {
                    const row = frm.add_child("lines");
                    row.account = account;
                    row.entry_type = side;
                    row.allocation_type = "Balancing";
                });
            frm.refresh_field("lines");
        }
    },

    unused_repeat_every_unit(frm) {
        // End of month on a daily or weekly rhythm would collapse every date in
        // a month onto one day. Clear it rather than let the save fail.
        if (!["Month", "Quarter", "Year"].includes(frm.doc.repeat_every_unit)
            && frm.doc.day_adjustment === "End of month") {
            frm.set_value("day_adjustment", "None");
            frappe.show_alert({
                message: __("End of month does not apply to a {0} rhythm, so it has been cleared.",
                            [frm.doc.repeat_every_unit.toLowerCase()]),
                indicator: "orange"
            });
        }
        refresh_plan(frm);
    },

    debit_account(frm)  { resolve_party(frm, "debit"); },
    credit_account(frm) { resolve_party(frm, "credit"); },

    debit_party_type(frm)  { frm.set_value("debit_party", null); },
    credit_party_type(frm) { frm.set_value("credit_party", null); },

    start_date: refresh_plan,
    duration_value: refresh_plan,
    duration_unit: refresh_plan,
    until_date: refresh_plan,
    post_on: refresh_plan,
    day_count_convention: refresh_plan,
    amount: refresh_plan,
    amount_type: refresh_plan,

    source_doctype(frm) {
        frm.set_value("source_document", null);
    },

    source_document(frm) {
        if (!frm.doc.source_document || !frm.doc.source_doctype) return;

        frappe.call({
            method: "neotec_recurring.api.source_document_defaults",
            args: { doctype: frm.doc.source_doctype, name: frm.doc.source_document },
            freeze: true
        }).then(r => {
            const v = r.message || {};

            frm.set_value("main_entry_date", v.main_entry_date);
            if (!frm.doc.start_date) frm.set_value("start_date", v.main_entry_date);
            if (!frm.doc.company && v.company) frm.set_value("company", v.company);
            if (!frm.doc.amount && v.amount) frm.set_value("amount", v.amount);

            // Party from the source is only a suggestion: whether it lands on
            // the party field or the dimension depends on the accounts chosen.
            if (v.suggested_party && !frm.doc.tracked_party) {
                frm.set_value("track_party", 1);
                frm.set_value("tracked_party_type", v.suggested_party_type);
                frm.set_value("tracked_party", v.suggested_party);
            }

            const control = v.credit_account || v.debit_account;
            if (control) {
                frappe.show_alert({
                    message: __("Control account on the source is {0}. Set the accounts below to suit the amortisation.", [control]),
                    indicator: "blue"
                });
            }
        });
    }
});

// Show the party fields only where ERPNext allows them, and offer every party
// type valid for that account rather than assuming Customer or Supplier.
function resolve_party(frm, side) {
    const account = frm.doc[side + "_account"];
    const type_field = side + "_party_type";
    const party_field = side + "_party";
    const flag_field = side + "_takes_party";

    if (!account) {
        frm.set_value(flag_field, 0);
        frm.set_value(type_field, null);
        frm.set_value(party_field, null);
        return;
    }

    frappe.call({
        method: "neotec_recurring.api.party_capability",
        args: { account }
    }).then(r => {
        const m = r.message || {};
        frm.set_value(flag_field, m.takes_party ? 1 : 0);

        if (!m.takes_party) {
            frm.set_value(type_field, null);
            frm.set_value(party_field, null);

            // A prepayment or expense account cannot carry a party. Point at the
            // dimension instead of leaving the user wondering why the field went.
            if (m.employee_dimension) {
                frm.set_df_property(m.employee_dimension, "description",
                    __("Use this to track the employee. {0} cannot carry a Party.",
                       [account]));
            }
            return;
        }

        // Restrict the picker to the party types ERPNext accepts here, which is
        // how Employee becomes selectable on a payable account.
        frm.set_query(type_field, () => ({
            filters: { name: ["in", m.valid_party_types || []] }
        }));

        if (!frm.doc[type_field] || !(m.valid_party_types || []).includes(frm.doc[type_field])) {
            frm.set_value(type_field, m.default_party_type);
        }

        frm.set_df_property(party_field, "reqd", 1);
    });
}

// The end date, the posting dates and the daily rate are all derived. This
// shows them as the user types, so nothing has to be saved to be checked.
function refresh_plan(frm) {
    if (!frm.doc.start_date || !frm.doc.duration_unit) return;
    if (frm.doc.duration_unit !== "Until a date" && !frm.doc.duration_value) return;

    frappe.call({
        method: "neotec_recurring.api.plan_preview",
        args: {
            start_date: frm.doc.start_date,
            duration_value: frm.doc.duration_value,
            duration_unit: frm.doc.duration_unit,
            until_date: frm.doc.until_date,
            post_on: frm.doc.post_on,
            day_count_convention: frm.doc.day_count_convention,
            amount: frm.doc.amount
        }
    }).then(r => {
        const m = r.message || {};
        if (m.error) return;

        frm.set_value("ends_on", m.end_date);
        frm.set_value("first_posting_date", m.first_posting_date);
        frm.set_value("number_of_postings", m.postings);
        frm.set_value("amount_per_day", m.amount_per_day);
        frm.set_value("schedule_summary", m.sentence);

        frm.dashboard.clear_headline();
        if (m.headline) frm.dashboard.set_headline_safe(m.headline);
    });
}

function preview(frm) {
    frappe.call({
        method: "neotec_recurring.api.preview_schedule_rows",
        args: { doc: JSON.stringify(frm.doc) },
        freeze: true, freeze_message: __("Building schedule")
    }).then(r => {
        const m = r.message || {};
        if (m.error) { frappe.msgprint({ title: __("Cannot preview"), message: m.error, indicator: "red" }); return; }

        const rows = (m.rows || []).map((x, i) => `
            <tr>
              <td style="color:#8D959E">${i + 1}</td>
              <td style="white-space:nowrap">${frappe.datetime.str_to_user(x.schedule_date)}</td>
              <td style="white-space:nowrap">${frappe.datetime.str_to_user(x.period_start)} &ndash; ${frappe.datetime.str_to_user(x.period_end)}</td>
              <td style="text-align:right"><b>${x.period_days}</b></td>
              <td style="text-align:right;color:#8D959E">${x.alt_days}</td>
              <td style="text-align:right;color:#8D959E">${x.days_left}</td>
              <td style="text-align:right">${x.amount_display}</td>
            </tr>`).join("");

        const many = (m.rows || []).length;
        const warn = many > 40
            ? `<div style="background:#FDF3E5;border-left:3px solid #E8942C;padding:9px 12px;
                 margin-bottom:12px;font-size:12px">
                 ${__("This schedule has {0} postings. If you meant a term of {0} days posted monthly, set Post every to 1 Month and Continue for to {0} Days.", [many])}
               </div>` : "";

        frappe.msgprint({
            title: __("Schedule Preview"),
            wide: true,
            message: `
              ${warn}
              <p style="margin-bottom:12px">${frappe.utils.escape_html(m.sentence || "")}</p>
              <div style="max-height:380px;overflow:auto">
              <table class="table table-bordered" style="font-size:12px;margin:0">
                <thead><tr>
                  <th style="width:36px"></th><th>${__("Posting date")}</th>
                  <th>${__("Covers")}</th>
                  <th style="text-align:right">${m.convention || __("Days")}</th>
                  <th style="text-align:right;color:#8D959E">${m.alt_convention || ""}</th>
                  <th style="text-align:right">${__("Days left")}</th>
                  <th style="text-align:right">${__("Amount")}</th>
                </tr></thead>
                <tbody>${rows}</tbody>
                <tfoot><tr style="font-weight:600">
                  <td colspan="3">${__("Total")}</td>
                  <td style="text-align:right">${m.total_days}</td>
                  <td style="text-align:right;color:#8D959E">${m.alt_total_days}</td>
                  <td></td>
                  <td style="text-align:right">${m.total_display}</td>
                </tr></tfoot>
              </table></div>`
        });
    });
}

function set_status(frm, status) {
    frappe.call({ method: "frappe.client.set_value",
        args: { doctype: frm.doctype, name: frm.doc.name, fieldname: "status", value: status }
    }).then(() => frm.reload_doc());
}

frappe.ui.form.on("Recurring Entry Line", {
    lines_add(frm, cdt, cdn) {
        frm.fields_dict.lines.grid.get_field("party_type").get_query = (doc, dt, dn) => {
            const row = locals[dt][dn];
            return { filters: { name: ["in", row.__valid_party_types || []] } };
        };
    },

    account(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (!row.account) return;

        frappe.call({
            method: "neotec_recurring.api.party_capability",
            args: { account: row.account }
        }).then(r => {
            const m = r.message || {};
            row.__valid_party_types = m.valid_party_types || [];

            if (!m.takes_party) {
                frappe.model.set_value(cdt, cdn, "party_type", null);
                frappe.model.set_value(cdt, cdn, "party", null);
                if (m.employee_dimension) {
                    frappe.show_alert({
                        message: __("{0} cannot carry a Party. Use the employee dimension on this row.",
                                    [row.account]),
                        indicator: "blue"
                    });
                }
                return;
            }

            if (!row.party_type || !m.valid_party_types.includes(row.party_type)) {
                frappe.model.set_value(cdt, cdn, "party_type", m.default_party_type);
            }
        });
    }
});


// Offer the dimension when the chosen party type has none. Without it, a party
// cannot reach the ledger on an accrued revenue or prepayment account.
function check_party_dimension(frm) {
    const party_type = frm.doc.tracked_party_type;

    frappe.call({
        method: "neotec_recurring.api.party_tracking_status",
        args: { party_type }
    }).then(r => {
        if ((r.message || {}).dimension) return;

        frappe.confirm(
            __("Tracking a {0} on accrual and prepayment accounts needs an Accounting Dimension over {0}. Create it now?", [party_type]),
            () => {
                frappe.call({
                    method: "neotec_recurring.api.create_party_dimension",
                    args: { document_type: party_type },
                    freeze: true,
                    freeze_message: __("Creating the dimension")
                }).then(res => {
                    frappe.show_alert({
                        message: (res.message || {}).created
                            ? __("{0} dimension created. Save the template to use it.", [party_type])
                            : __("{0} dimension already exists.", [party_type]),
                        indicator: "green"
                    });
                    frm.reload_doc();
                });
            },
            () => frappe.msgprint({
                title: __("Party will not reach the ledger"),
                indicator: "orange",
                message: __("Without the dimension, the {0} is recorded only on lines whose account is receivable or payable. On other lines the name goes in the narration.", [party_type])
            })
        );
    });
}
