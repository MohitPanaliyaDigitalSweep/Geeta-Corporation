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
        async: false,
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
    var lf = uom.litre_factor || 1;

    var pcs = box * nf;
    var ltr_per_piece = lf / nf;
    var total_litre = box * lf;

    frappe.model.set_value(cdt, cdn, "fe_pcs", pcs);
    frappe.model.set_value(cdt, cdn, "fe_ltr", ltr_per_piece);
    frappe.model.set_value(cdt, cdn, "fe_total_ltr", total_litre);
    frappe.model.set_value(cdt, cdn, "qty", pcs);
    frappe.model.set_value(cdt, cdn, "uom", "Nos");

    fast_entry_app.update_total_litre_summary(frm);
};

fast_entry_app.update_total_litre_summary = function(frm) {
    var total = 0;
    var items = frm.doc.items || [];
    for (var i = 0; i < items.length; i++) {
        if (items[i].fe_total_ltr) {
            total += flt(items[i].fe_total_ltr);
        } else if (items[i].fe_box) {
            var uom = fast_entry_app._uom_cache[items[i].item_code];
            if (uom) {
                total += flt(items[i].fe_box) * (uom.litre_factor || 1);
            }
        }
    }

    var $target = frm.fields_dict.items.$wrapper;
    var $summary = $target.find(".fe-total-litre-summary");
    if (!$summary.length) {
        $summary = $(
            '<div class="fe-total-litre-summary" style="margin-top:8px;padding:8px 12px;background:#f0fdf4;border:1px solid #86efac;border-radius:6px;display:flex;align-items:center;gap:12px;">' +
            '<span style="font-size:12px;font-weight:600;color:#166534;">Total Litre:</span>' +
            '<span class="fe-total-litre-value" style="font-size:18px;font-weight:700;color:#15803d;">0.00</span>' +
            '<span style="font-size:11px;color:#6b7280;margin-left:auto;">(auto-calculated from Box × Kg/Litre per Box)</span>' +
            '</div>'
        );
        $target.after($summary);
    }
    $summary.find(".fe-total-litre-value").text(total.toFixed(2));
};

frappe.ui.form.on("Purchase Invoice", {
    refresh: function(frm) {
        frappe.ui.form.on("Purchase Invoice Item", {
            item_code: function(frm, cdt, cdn) {
                fast_entry_app.load_uom(frm, cdt, cdn);
            },
            fe_box: function(frm, cdt, cdn) {
                fast_entry_app.load_uom(frm, cdt, cdn);
            },
            items_remove: function(frm) {
                fast_entry_app.update_total_litre_summary(frm);
            }
        });
        fast_entry_app.update_total_litre_summary(frm);
    }
});

frappe.ui.form.on("Sales Invoice", {
    refresh: function(frm) {
        frappe.ui.form.on("Sales Invoice Item", {
            item_code: function(frm, cdt, cdn) {
                fast_entry_app.load_uom(frm, cdt, cdn);
            },
            fe_box: function(frm, cdt, cdn) {
                fast_entry_app.load_uom(frm, cdt, cdn);
            },
            items_remove: function(frm) {
                fast_entry_app.update_total_litre_summary(frm);
            }
        });
        fast_entry_app.update_total_litre_summary(frm);
    }
});
