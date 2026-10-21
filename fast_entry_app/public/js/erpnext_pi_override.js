frappe.provide("fast_entry_app");
fast_entry_app._uom_cache = {};
fast_entry_app._setting = {};

fast_entry_app.load_uom = function(frm, cdt, cdn, source) {
    var row = locals[cdt][cdn];
    if (!row.item_code) return;

    if (fast_entry_app._uom_cache[row.item_code]) {
        setTimeout(function() {
            fast_entry_app.calc_row(frm, cdt, cdn, source);
        }, 50);
        return;
    }

    frappe.call({
        method: "fast_entry_app.api.item.get_item_uom",
        args: { item_code: row.item_code },
        callback: function(r) {
            if (r && r.message) {
                fast_entry_app._uom_cache[row.item_code] = r.message;
                // Small delay so parent doctype's own item_code callback
                // (e.g. Stock Entry's get_item_details) finishes first.
                setTimeout(function() {
                    fast_entry_app.calc_row(frm, cdt, cdn, source);
                }, 50);
            } else {
                fast_entry_app._setting[cdn] = false;
            }
        }
    });
};

fast_entry_app.calc_row = function(frm, cdt, cdn, source) {
    fast_entry_app._setting[cdn] = true;
    var row = locals[cdt][cdn];
    var uom = fast_entry_app._uom_cache[row.item_code];
    if (!uom) return;

    var nf = uom.nos_factor || 1;
    var ltr_per_piece = uom.litre_factor || 0;

    // Write only real changes: set_value fires ERPNext's UOM/amount handlers,
    // and gratuitous writes make it recalculate over our values.
    var set = function(field, value) {
        value = flt(value) || 0;
        if (flt(row[field]) !== value) {
            frappe.model.set_value(cdt, cdn, field, value);
        }
    };

    var box = flt(row.fe_box) || 0;
    var pcs = flt(row.fe_pcs) || 0;

    if (source === "pcs") {
        // PCS drives Box back the other way, so both stay independently editable.
        set("fe_box", nf ? pcs / nf : 0);
    } else if (source === "box") {
        set("fe_pcs", box * nf);
    } else if (!box && !pcs) {
        // Fresh item pick: seed Box/PCS from the Item master exactly like the
        // fast entry pages do (one box when the item is packed in a Box, else
        // one piece so qty is never zero).
        box = uom.has_box ? 1 : 0;
        set("fe_box", box);
        set("fe_pcs", box ? box * nf : 1);
    } else if (!pcs) {
        set("fe_pcs", box ? box * nf : 1);
    }

    // Pack breakdown always auto-fills (Box/PCS/LTR/Total LTR).
    set("fe_ltr", ltr_per_piece);
    set("fe_total_ltr", flt(row.fe_pcs || 0) * ltr_per_piece);

    // Qty is always PCS (pieces) in every doctype, exactly like Sales/Purchase
    // Invoice: the app books qty = fe_pcs in the item's invoice UOM.
    var invoice_uom = uom.invoice_uom || "Nos";
    if (row.uom !== invoice_uom) {
        frappe.model.set_value(cdt, cdn, "uom", invoice_uom);
    }
    set("conversion_factor", flt(uom.conversion_factor) || 1);
    set("qty", flt(row.fe_pcs) || 0);
    fast_entry_app._setting[cdn] = false;
};

// ---- item row wiring: Box and PCS are both editable and drive each other ----

function _fe_item_handlers() {
    return {
        item_code: function(frm, cdt, cdn) {
            fast_entry_app._setting[cdn] = true;
            fast_entry_app.load_uom(frm, cdt, cdn, "item");
        },
        fe_box: function(frm, cdt, cdn) {
            fast_entry_app.load_uom(frm, cdt, cdn, "box");
        },
        fe_pcs: function(frm, cdt, cdn) {
            fast_entry_app.load_uom(frm, cdt, cdn, "pcs");
        },
        qty: function(frm, cdt, cdn) {
            // Re-apply calc when the parent doctype's own item_code handler
            // sets qty (e.g. Stock Entry's get_item_details). This ensures
            // fe_* fields are populated and qty ends up as PCS.
            if (fast_entry_app._setting[cdn]) return;
            var row = locals[cdt][cdn];
            if (row && row.item_code && fast_entry_app._uom_cache[row.item_code]) {
                fast_entry_app.calc_row(frm, cdt, cdn, "item");
            }
        }
    };
}

// All item child tables that carry fe_box/fe_pcs/fe_ltr/fe_total_ltr.
var _FE_ITEM_TABLES = [
    "Purchase Invoice Item", "Sales Invoice Item", "Quotation Item",
    "Sales Order Item", "Purchase Order Item", "Delivery Note Item",
    "Purchase Receipt Item", "Stock Entry Detail",
    "Asset Capitalization Service Item", "Asset Movement Item",
    "BOM Creator Item", "BOM Item", "BOM Secondary Item", "BOM Website Item",
    "Bill of Entry Item", "Blanket Order Item", "Installation Note Item",
    "Landed Cost Item", "Material Request Item", "Opportunity Item",
    "POS Invoice Item", "Packed Item", "Packing Slip Item", "Pick List Item",
    "Product Bundle Item", "Request for Quotation Item", "Serial and Batch Entry",
    "Stock Reconciliation Item", "Subcontracting Inward Order Item",
    "Subcontracting Inward Order Service Item", "Subcontracting Order Item",
    "Subcontracting Order Service Item", "Subcontracting Receipt Item",
    "Supplier Quotation Item", "Work Order Additional Item"
];
_FE_ITEM_TABLES.forEach(function(dt) {
    try { frappe.ui.form.on(dt, _fe_item_handlers()); } catch (e) { /* doctype may not be installed */ }
});

// ---- update_stock defaults on, but stays editable ----

function default_update_stock(frm) {
    // Only seed brand-new documents. Never fight the user on a saved doc, and
    // never make the field read-only -- service / non-stock invoices must still
    // be possible.
    if (!frm.is_new()) return;
    if (frm.doc.update_stock) return;
    if (frm.__fe_update_stock_seeded) return;
    frm.__fe_update_stock_seeded = true;
    frm.set_value("update_stock", 1);
}

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
        default_update_stock(frm);
    }
});

frappe.ui.form.on("Purchase Invoice", {
    refresh: function(frm) {
        add_send_buttons(frm);
        default_update_stock(frm);
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
