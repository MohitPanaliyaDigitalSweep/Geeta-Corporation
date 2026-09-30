frappe.provide("fast_entry_app");
fast_entry_app._uom_cache = {};

fast_entry_app.load_uom = function(frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    if (!row.item_code) return;

    if (fast_entry_app._uom_cache[row.item_code]) {
        fast_entry_app.calc_row(frm, cdt, cdn);
        return;
    }

    frappe.call({
        method: "fast_entry_app.api.item.get_item_uom",
        args: { item_code: row.item_code },
        callback: function(r) {
            if (r && r.message) {
                fast_entry_app._uom_cache[row.item_code] = r.message;
                fast_entry_app.calc_row(frm, cdt, cdn);
            }
        }
    });
};

fast_entry_app.calc_row = function(frm, cdt, cdn) {
    var row = locals[cdt][cdn];
    var uom = fast_entry_app._uom_cache[row.item_code];
    if (!uom) return;

    var box = flt(row.fe_box) || 0;
    var nf = uom.nos_factor || 1;
    var ltr_per_piece = uom.litre_factor || 0;

    var pcs = box * nf;
    var total_litre = pcs * ltr_per_piece;

    frappe.model.set_value(cdt, cdn, "fe_pcs", pcs);
    frappe.model.set_value(cdt, cdn, "fe_ltr", ltr_per_piece);
    frappe.model.set_value(cdt, cdn, "fe_total_ltr", total_litre);
    frappe.model.set_value(cdt, cdn, "qty", pcs);
    frappe.model.set_value(cdt, cdn, "uom", "Nos");
};

frappe.ui.form.on("Purchase Invoice Item", {
    item_code: function(frm, cdt, cdn) {
        fast_entry_app.load_uom(frm, cdt, cdn);
    },
    fe_box: function(frm, cdt, cdn) {
        fast_entry_app.load_uom(frm, cdt, cdn);
    }
});

frappe.ui.form.on("Sales Invoice Item", {
    item_code: function(frm, cdt, cdn) {
        fast_entry_app.load_uom(frm, cdt, cdn);
    },
    fe_box: function(frm, cdt, cdn) {
        fast_entry_app.load_uom(frm, cdt, cdn);
    }
});

// --- Send buttons for PI, SI, and Quotation ---

function _open_dialog(title, field_label, default_val, on_submit) {
    var d = new frappe.ui.Dialog({
        title: __(title),
        fields: [
            {fieldname: "value", fieldtype: "Data", label: __(field_label), reqd: 1, default: default_val || ""}
        ],
        primary_action_label: __("Send"),
        primary_action: function(values) {
            d.hide();
            on_submit(values.value);
        }
    });
    d.show();
    return d;
}

function _prompt_send_missing_field(info, send_type, doctype) {
    const is_mobile = info.missing_field === "mobile_no";
    const label = is_mobile ? "Mobile Number" : "Email Address";
    const fieldname = info.missing_field;

    var d = new frappe.ui.Dialog({
        title: __("Enter {0} for {1}", [label, info.party_name]),
        fields: [
            {fieldname: "value", fieldtype: is_mobile ? "Phone" : "Data", label: __(label), reqd: 1}
        ],
        primary_action_label: __("Save & Send"),
        primary_action: function(values) {
            d.hide();
            frappe.call({
                method: "fast_entry_app.api.invoice_send.update_party_field",
                args: {
                    party_type: info.party_type,
                    party_name: info.party_name,
                    fieldname: fieldname,
                    value: values.value,
                },
                callback: function() {
                    frappe.show_alert({ message: label + " saved to " + info.party_name, indicator: "green" });
                    if (doctype === "Sales Invoice") {
                        if (send_type === "whatsapp") _si_whatsapp(info.invoice_name, values.value);
                        else _si_email(info.invoice_name, values.value);
                    } else if (doctype === "Quotation") {
                        if (send_type === "whatsapp") _qtn_whatsapp(info.invoice_name, values.value);
                        else _qtn_email(info.invoice_name, values.value);
                    } else {
                        if (send_type === "whatsapp") _pi_whatsapp(info.invoice_name, values.value);
                        else _pi_email(info.invoice_name, values.value);
                    }
                },
            });
        }
    });
    d.show();
}

function _download_pdf(pdf_url) {
    const a = document.createElement("a");
    a.href = pdf_url;
    a.download = "";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
}

function _si_whatsapp(invoice_name, number) {
    const args = { invoice_name: invoice_name };
    if (number) args.number = number;
    frappe.call({
        method: "fast_entry_app.api.invoice_send.send_invoice_whatsapp",
        args: args,
        callback: function(r) {
            if (r.message && r.message.ok) {
                frappe.show_alert({message: __("WhatsApp sent to {0} (msg {1})", [r.message.chat_id, r.message.message_id || "sent"]), indicator: "green"});
            } else if (r.message && r.message.missing_field) {
                r.message.invoice_name = invoice_name;
                _prompt_send_missing_field(r.message, "whatsapp", "Sales Invoice");
            } else if (r.message && r.message.not_configured) {
                frappe.show_alert({message: r.message.message, indicator: "orange"});
            } else if (r.message) {
                frappe.show_alert({message: r.message.message || __("WhatsApp send failed"), indicator: "red"});
            }
        }
    });
}

function _si_email(invoice_name, recipient) {
    const args = { invoice_name: invoice_name };
    if (recipient) args.recipient = recipient;
    frappe.call({
        method: "fast_entry_app.api.invoice_send.send_invoice_email",
        args: args,
        callback: function(r) {
            if (r.message && r.message.ok) {
                frappe.show_alert({message: __("PDF downloading for {0}", [r.message.name]), indicator: "green"});
                if (r.message.pdf_url) _download_pdf(r.message.pdf_url);
                if (r.message.mailto) window.open(r.message.mailto, "_blank");
            } else if (r.message && r.message.missing_field) {
                r.message.invoice_name = invoice_name;
                _prompt_send_missing_field(r.message, "email", "Sales Invoice");
            }
        }
    });
}

function _pi_whatsapp(invoice_name, number) {
    const args = { purchase_invoice_name: invoice_name };
    if (number) args.number = number;
    frappe.call({
        method: "fast_entry_app.api.invoice_send.send_purchase_invoice_whatsapp",
        args: args,
        callback: function(r) {
            if (r.message && r.message.ok) {
                frappe.show_alert({message: __("WhatsApp sent to {0} (msg {1})", [r.message.chat_id, r.message.message_id || "sent"]), indicator: "green"});
            } else if (r.message && r.message.missing_field) {
                r.message.invoice_name = invoice_name;
                _prompt_send_missing_field(r.message, "whatsapp", "Purchase Invoice");
            } else if (r.message && r.message.not_configured) {
                frappe.show_alert({message: r.message.message, indicator: "orange"});
            } else if (r.message) {
                frappe.show_alert({message: r.message.message || __("WhatsApp send failed"), indicator: "red"});
            }
        }
    });
}

function _pi_email(invoice_name, recipient) {
    const args = { purchase_invoice_name: invoice_name };
    if (recipient) args.recipient = recipient;
    frappe.call({
        method: "fast_entry_app.api.invoice_send.send_purchase_invoice_email",
        args: args,
        callback: function(r) {
            if (r.message && r.message.ok) {
                frappe.show_alert({message: __("PDF downloading for {0}", [r.message.name]), indicator: "green"});
                if (r.message.pdf_url) _download_pdf(r.message.pdf_url);
                if (r.message.mailto) window.open(r.message.mailto, "_blank");
            } else if (r.message && r.message.missing_field) {
                r.message.invoice_name = invoice_name;
                _prompt_send_missing_field(r.message, "email", "Purchase Invoice");
            }
        }
    });
}

function _qtn_whatsapp(quotation_name, number) {
    const args = { quotation_name: quotation_name };
    if (number) args.number = number;
    frappe.call({
        method: "fast_entry_app.api.invoice_send.send_quotation_whatsapp",
        args: args,
        callback: function(r) {
            if (r.message && r.message.ok) {
                frappe.show_alert({message: __("WhatsApp sent to {0} (msg {1})", [r.message.chat_id, r.message.message_id || "sent"]), indicator: "green"});
            } else if (r.message && r.message.missing_field) {
                r.message.invoice_name = quotation_name;
                _prompt_send_missing_field(r.message, "whatsapp", "Quotation");
            } else if (r.message && r.message.not_configured) {
                frappe.show_alert({message: r.message.message, indicator: "orange"});
            } else if (r.message) {
                frappe.show_alert({message: r.message.message || __("WhatsApp send failed"), indicator: "red"});
            }
        }
    });
}

function _qtn_email(quotation_name, recipient) {
    const args = { quotation_name: quotation_name };
    if (recipient) args.recipient = recipient;
    frappe.call({
        method: "fast_entry_app.api.invoice_send.send_quotation_email",
        args: args,
        callback: function(r) {
            if (r.message && r.message.ok) {
                frappe.show_alert({message: __("Email sent to {0}", [r.message.email]), indicator: "green"});
            } else if (r.message && r.message.missing_field) {
                r.message.invoice_name = quotation_name;
                _prompt_send_missing_field(r.message, "email", "Quotation");
            }
        }
    });
}

function add_send_buttons(frm) {
    if (frm.doc.docstatus !== 1) return;

    const is_si = frm.doctype === "Sales Invoice";
    const is_pi = frm.doctype === "Purchase Invoice";

    if (is_si) {
        frm.add_custom_button(__("WhatsApp"), function() {
            _si_whatsapp(frm.doc.name);
        }, __("Send"));

        frm.add_custom_button(__("Email"), function() {
            frappe.db.get_value("Customer", frm.doc.customer, "email_id").then(function(r) {
                var email = (r && r.message) || "";
                if (email) {
                    _si_email(frm.doc.name, email);
                } else {
                    _open_dialog("Send Email", "Email To", "", function(val) {
                        _si_email(frm.doc.name, val);
                    });
                }
            });
        }, __("Send"));
    }

    if (is_pi) {
        frm.add_custom_button(__("WhatsApp"), function() {
            _pi_whatsapp(frm.doc.name);
        }, __("Send"));

        frm.add_custom_button(__("Email"), function() {
            frappe.db.get_value("Supplier", frm.doc.supplier, "email_id").then(function(r) {
                var email = (r && r.message) || "";
                if (email) {
                    _pi_email(frm.doc.name, email);
                } else {
                    _open_dialog("Send Email", "Email To", "", function(val) {
                        _pi_email(frm.doc.name, val);
                    });
                }
            });
        }, __("Send"));
    }
}

frappe.ui.form.on("Sales Invoice", {
    refresh: function(frm) {
        add_send_buttons(frm);
    }
});

frappe.ui.form.on("Purchase Invoice", {
    refresh: function(frm) {
        add_send_buttons(frm);
    }
});

frappe.ui.form.on("Quotation", {
    refresh: function(frm) {
        if (frm.doc.docstatus === 2) return;

        frm.add_custom_button(__("WhatsApp"), function() {
            _qtn_whatsapp(frm.doc.name);
        }, __("Send"));

        frm.add_custom_button(__("Email"), function() {
            frappe.db.get_value("Customer", frm.doc.party_name, "email_id").then(function(r) {
                var email = (r && r.message) || "";
                if (email) {
                    _qtn_email(frm.doc.name, email);
                } else {
                    _open_dialog("Send Email", "Email To", "", function(val) {
                        _qtn_email(frm.doc.name, val);
                    });
                }
            });
        }, __("Send"));
    }
});
