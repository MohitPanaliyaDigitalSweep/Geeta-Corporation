frappe.provide("fast_entry_app");

frappe.pages["fast-purchase-entry"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Fast Purchase Entry"),
        single_column: true,
    });
    fast_entry_app.purchase_page = new fast_entry_app.PurchaseEntry(wrapper);
};

fast_entry_app.PurchaseEntry = class PurchaseEntry {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.items = [];
        this.settings = {};
        this.supplier_details = {};
        this.last_saved_name = null;
        this.active_dropdown = null;
        this.active_input = null;
        this.build_global_dropdown();
        this.build();
    }

    flt(v) { return parseFloat(v) || 0; }

    build_global_dropdown() {
        this.$gd = $('<div class="fe-global-dropdown"></div>').appendTo("body");
        this.$gd.on("mousedown", ".fe-dropdown-item", (e) => {
            e.preventDefault();
            if (this._dropdown_select_handler) this._dropdown_select_handler($(e.currentTarget));
            this.hide_global_dropdown();
        });
        $(document).on("mousedown", (e) => {
            if (!$(e.target).closest(".fe-global-dropdown, .fe-input, .fe-grid-input").length) {
                this.hide_global_dropdown();
            }
        });
    }

    show_global_dropdown($input, items_html, select_handler) {
        this._dropdown_select_handler = select_handler;
        this.$gd.html(items_html).show();
        const rect = $input[0].getBoundingClientRect();
        this.$gd.css({
            top: rect.bottom + 1,
            left: rect.left,
            width: Math.max(rect.width, 250),
        });
        this.active_input = $input;
    }

    hide_global_dropdown() {
        this.$gd.hide().empty();
        this.active_input = null;
    }

    build() {
        try {
            this.$root = $(this.wrapper.page.main);
            this.$root.html(this.get_html());
            this.bind_elements();
            this.add_empty_row();
            this.bind_keyboard();
            this.update_totals();
        } catch(e) {
            console.error("Fast Entry build error:", e);
            frappe.msgprint({title: "Build Error", indicator: "red", message: String(e)});
        }
    }

    get_html() {
        return `<div class="fast-entry-container">
            <div class="fe-header-section">
                <div class="fe-header-row">
                    <div class="fe-field">
                        <label>Company <span class="reqd">*</span></label>
                        <select class="fe-input" id="fe-company"></select>
                    </div>
                    <div class="fe-field fe-field-wide">
                        <label>Supplier <span class="reqd">*</span></label>
                        <div class="fe-input-wrap fe-autocomplete-wrap">
                            <input type="text" class="fe-input" id="fe-supplier" placeholder="Type to search..." autocomplete="off" />
                        </div>
                        <div class="fe-party-balance" id="fe-supplier-balance"></div>
                    </div>
                </div>
                <div class="fe-header-row">
                    <div class="fe-field"><label>Bill No <span class="reqd">*</span></label><input type="text" class="fe-input" id="fe-bill-no" /></div>
                    <div class="fe-field"><label>Bill Date <span class="reqd">*</span></label><input type="date" class="fe-input" id="fe-bill-date" /></div>
                    <div class="fe-field"><label>GST Type</label>
                        <select class="fe-input" id="fe-gst-type">
                            <option value="intra">Intra-State (CGST+SGST)</option>
                            <option value="inter">Inter-State (IGST)</option>
                        </select>
                    </div>
                    <div class="fe-field"><label>Tax Override</label>
                        <select class="fe-input" id="fe-tax-template">
                            <option value="">Per Item Rate</option>
                            <option value="5">Override 5%</option>
                            <option value="12">Override 12%</option>
                            <option value="18">Override 18%</option>
                            <option value="28">Override 28%</option>
                        </select>
                    </div>
                    <div class="fe-field"><label>Warehouse</label>
                        <div class="fe-input-wrap fe-autocomplete-wrap">
                            <input type="text" class="fe-input" id="fe-warehouse" placeholder="Default WH" autocomplete="off" />
                        </div>
                    </div>
                    <div class="fe-field"><label class="fe-checkbox-label"><input type="checkbox" class="fe-input" id="fe-stock-impact" checked /> Stock Impact</label></div>
                </div>
            </div>
            <div class="fe-grid-section">
                <div class="fe-grid-wrap">
                    <table class="fe-grid" id="fe-items-grid">
                        <thead><tr>
                            <th class="fe-col-num">#</th>
                            <th class="fe-col-item">Item</th>
                            <th class="fe-col-box">Box</th>
                            <th class="fe-col-pcs">PCS</th>
                            <th class="fe-col-ltr">LTR</th>
                            <th class="fe-col-qty">Total Litre</th>
                            <th class="fe-col-rate">Rate</th>
                            <th class="fe-col-amount">Amount</th>
                            <th class="fe-col-action"></th>
                        </tr></thead>
                        <tbody id="fe-grid-body"></tbody>
                        <tfoot id="fe-grid-footer">
                            <tr class="fe-grid-total-row">
                                <td colspan="2" style="text-align:center;font-weight:700;"><span id="fe-total-count">0</span> Items</td>
                                <td class="fe-col-box" id="fe-total-box">0</td>
                                <td class="fe-col-pcs" id="fe-total-pcs">0</td>
                                <td class="fe-col-ltr" id="fe-total-ltr">0.00</td>
                                <td class="fe-col-qty" id="fe-total-qty">0.00</td>
                                <td class="fe-col-rate"></td>
                                <td class="fe-col-amount" id="fe-total-amount">0.00</td>
                                <td class="fe-col-action"></td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
                <div class="fe-grid-toolbar">
                    <button class="fe-btn fe-btn-sm" id="fe-add-row" title="Add Row (F3)"><i class="fa fa-plus"></i> Add Row</button>
                </div>
            </div>
            <div class="fe-totals-section">
                <div class="fe-totals-left">
                    <div class="fe-field fe-field-sm"><label>Discount %</label><input type="number" class="fe-input fe-input-sm" id="fe-discount-pct" value="0" min="0" max="100" step="any" /></div>
                    <div class="fe-field fe-field-sm"><label>Discount Amt</label><input type="number" class="fe-input fe-input-sm" id="fe-discount" value="0" min="0" /></div>
                    <div class="fe-field fe-field-sm"><label>Freight</label><input type="number" class="fe-input fe-input-sm" id="fe-freight" value="0" min="0" /></div>
                </div>
                <div class="fe-totals-right">
                    <table class="fe-totals-table">
                        <tr><td>Sub Total</td><td id="fe-sub-total">0.00</td></tr>
                        <tr><td>Discount</td><td id="fe-total-discount">-0.00</td></tr>
                        <tr><td>Freight</td><td id="fe-total-freight">+0.00</td></tr>
                        <tr class="fe-freight-gst-row" style="display:none"><td>Freight GST @18%</td><td id="fe-freight-gst">0.00</td></tr>
                        <tr class="fe-tax-row" id="fe-cgst-row"><td>CGST</td><td id="fe-cgst-amt">0.00</td></tr>
                        <tr class="fe-tax-row" id="fe-sgst-row"><td>SGST</td><td id="fe-sgst-amt">0.00</td></tr>
                        <tr class="fe-tax-row" id="fe-igst-row" style="display:none"><td>IGST</td><td id="fe-igst-amt">0.00</td></tr>
                        <tr><td>Round Off</td><td id="fe-round-off">0.00</td></tr>
                        <tr class="fe-net-total"><td><b>Net Total</b></td><td><b id="fe-net-total">0.00</b></td></tr>
                    </table>
                </div>
            </div>
            <div class="fe-actions-section">
                <div class="fe-actions-left">
                    <span class="fe-shortcut-hint">Ctrl+S: Save</span>
                    <span class="fe-shortcut-hint">Ctrl+P: Print</span>
                    <span class="fe-shortcut-hint">F2: Save &amp; New</span>
                    <span class="fe-shortcut-hint">F3: Add Row</span>
                </div>
                <div class="fe-actions-right">
                    <button class="fe-btn fe-btn-wa" id="fe-wa-send" title="Send purchase invoice PDF via WhatsApp"><i class="fa fa-whatsapp"></i> WhatsApp</button>
                    <button class="fe-btn fe-btn-email" id="fe-email-send" title="Send purchase invoice PDF via Email"><i class="fa fa-envelope"></i> Email</button>
                    <button class="fe-btn fe-btn-primary" id="fe-save"><i class="fa fa-check"></i> Save (Ctrl+S)</button>
                    <button class="fe-btn" id="fe-print-btn"><i class="fa fa-print"></i> Print (Ctrl+P)</button>
                    <button class="fe-btn fe-btn-success" id="fe-save-new"><i class="fa fa-forward"></i> Save &amp; New (F2)</button>
                </div>
            </div>
            <div class="fe-status-bar" id="fe-status-bar"></div>
        </div>`;
    }

    bind_elements() {
        this.$grid_body = this.$root.find("#fe-grid-body");
        this.$company = this.$root.find("#fe-company");
        this.$supplier = this.$root.find("#fe-supplier");
        this.$supplier_balance = this.$root.find("#fe-supplier-balance");
        this.$bill_no = this.$root.find("#fe-bill-no");
        this.$bill_date = this.$root.find("#fe-bill-date");
        this.$gst_type = this.$root.find("#fe-gst-type");
        this.$tax_template = this.$root.find("#fe-tax-template");
        this.$warehouse = this.$root.find("#fe-warehouse");
        this.$stock_impact = this.$root.find("#fe-stock-impact");
        this.$discount = this.$root.find("#fe-discount");
        this.$discount_pct = this.$root.find("#fe-discount-pct");
        this.$freight = this.$root.find("#fe-freight");
        this.$status_bar = this.$root.find("#fe-status-bar");

        this.$bill_date.val(frappe.datetime.get_today());
        this.load_companies();

        this.$root.find("#fe-add-row").on("click", () => this.add_empty_row());
        this.$root.find("#fe-save").on("click", () => this.save());
        this.$root.find("#fe-save-new").on("click", () => this.save_and_new());
        this.$root.find("#fe-print-btn").on("click", () => this.print_last());
        this.$root.find("#fe-wa-send").on("click", () => this.send_whatsapp());
        this.$root.find("#fe-email-send").on("click", () => this.send_email());
        this.$discount.on("input", () => {
            const sub_total = this.items.reduce((s, r) => s + (r.amount || 0), 0);
            const amt = this.flt(this.$discount.val());
            if (sub_total > 0) {
                this.$discount_pct.val((amt / sub_total * 100).toFixed(2));
            }
            this.update_totals();
        });
        this.$discount_pct.on("input", () => {
            const sub_total = this.items.reduce((s, r) => s + (r.amount || 0), 0);
            const pct = this.flt(this.$discount_pct.val());
            this.$discount.val((sub_total * pct / 100).toFixed(2));
            this.update_totals();
        });
        this.$freight.on("input", () => this.update_totals());
        this.$tax_template.on("change", () => this.update_totals());
        this.$gst_type.on("change", () => this.update_totals());

        this.bind_supplier_autocomplete();
        this.bind_warehouse_autocomplete();
    }

    load_companies() {
        const self = this;
        frappe.call({
            method: "frappe.client.get_list",
            args: { doctype: "Company", filters: {}, fields: ["name"], limit_page_length: 100 },
            callback: function(r) {
                const companies = r.message || [];
                self.$company.empty().append('<option value="">Select Company</option>');
                companies.forEach(c => self.$company.append(`<option value="${c.name}">${c.name}</option>`));
                if (companies.length === 1) {
                    self.$company.val(companies[0].name);
                } else {
                    var last = localStorage.getItem("fe_last_company");
                    if (last && companies.find(c => c.name === last)) {
                        self.$company.val(last);
                    }
                }
                self.$company.on("change", function() {
                    localStorage.setItem("fe_last_company", $(this).val());
                });
            }
        });
    }

    add_empty_row() {
        const idx = this.items.length + 1;
        const row = { idx, item_code:"", item_name:"", box:0, pcs:0, ltr:0, qty:0, rate:0, amount:0, uom:"", nos_factor:1, litre_factor:0, stock_uom:"", warehouse:"", gst_rate:0, wh_stock:0, company_stock:0 };
        this.items.push(row);
        this.render_row(row);
    }

    render_row(row) {
        const tr = document.createElement("tr");
        tr.dataset.idx = row.idx;
        tr.className = "fe-grid-row";
        row._tr = tr;
        tr.innerHTML = `
            <td class="fe-col-num">${row.idx}</td>
            <td class="fe-col-item">
                <div class="fe-input-wrap fe-autocomplete-wrap">
                    <input type="text" class="fe-grid-input fe-item-input" data-field="item_code" value="${row.item_name||row.item_code}" placeholder="Search..." autocomplete="off" />
                </div>
                <div class="fe-item-code">${row.item_code||""}</div>
                <div class="fe-item-stock"></div>
            </td>
            <td class="fe-col-box"><input type="number" class="fe-grid-input fe-num-input" data-field="box" value="${row.box||""}" min="0" step="1" /></td>
            <td class="fe-col-pcs"><input type="number" class="fe-grid-input fe-num-input" data-field="pcs" value="${row.pcs||""}" min="0" /></td>
            <td class="fe-col-ltr"><input type="number" class="fe-grid-input fe-num-input" data-field="ltr" value="${row.ltr||""}" min="0" step="0.01" /></td>
            <td class="fe-col-qty"><input type="number" class="fe-grid-input fe-num-input" data-field="qty" value="${row.qty||""}" min="0" readonly /></td>
            <td class="fe-col-rate"><input type="number" class="fe-grid-input fe-num-input" data-field="rate" value="${row.rate||""}" min="0" step="0.01" /></td>
            <td class="fe-col-amount"><span class="fe-amount-display">${this.fmt_currency(row.amount)}</span></td>
            <td class="fe-col-action"><button class="fe-btn-icon fe-delete-row" title="Delete"><i class="fa fa-times"></i></button></td>`;
        this.$grid_body[0].appendChild(tr);
        this.bind_row_events(tr, row);
    }

    fmt_currency(v) { return (v||0).toFixed(2); }

    bind_row_events(tr, row) {
        const self = this;
        const $item_input = $(tr).find(".fe-item-input");

        $item_input.on("input", function() {
            const val = $(this).val();
            const $inp = $(this);
            if (val.length < 1) { self.hide_global_dropdown(); return; }
            self.search_items(val, function(results) {
                let html = "";
                results.forEach(function(item) {
                    const uom_info = (item.uoms && item.uoms.length > 1)
                        ? ` <span class="fe-dd-secondary">(${item.uoms.find(u => u.conversion_factor !== 1)?.uom || item.stock_uom})</span>`
                        : "";
                    html += `<div class="fe-dropdown-item" data-value="${item.item_code}" data-name="${item.item_name}" data-uoms='${JSON.stringify(item.uoms || [])}'><span class="fe-dd-primary">${item.item_name||item.item_code}</span><span class="fe-dd-secondary">${item.item_code}</span>${uom_info}</div>`;
                });
                if (html) {
                    self.show_global_dropdown($inp, html, function($el) {
                        $inp.val($el.data("name") || $el.data("value")).attr("data-item-code", $el.data("value"));
                        let uoms = [];
                        try { uoms = JSON.parse($el.attr("data-uoms") || "[]"); } catch(ex) {}
                        self.on_item_selected(row, $el.data("value"), $el.data("name"), tr, uoms);
                    });
                } else {
                    self.hide_global_dropdown();
                }
            });
        });

        $item_input.on("focus", function() { if ($(this).val().length >= 1) $(this).trigger("input"); });

        $item_input.on("keydown", function(e) {
            const $items = self.$gd.find(".fe-dropdown-item");
            const $active = $items.filter(".active");
            if (e.key === "ArrowDown") {
                e.preventDefault();
                if (!$active.length) $items.first().addClass("active");
                else { $active.removeClass("active").next().addClass("active"); }
                self.$gd.scrollTop($items.filter(".active").position()?.top + self.$gd.scrollTop() - 40);
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                if (!$active.length) $items.last().addClass("active");
                else { $active.removeClass("active").prev().addClass("active"); }
            } else if (e.key === "Enter") {
                e.preventDefault();
                if ($active.length) $active.trigger("mousedown");
                else if ($(this).val()) self.on_item_selected(row, $(this).val(), "", tr, []);
            } else if (e.key === "Escape") {
                self.hide_global_dropdown();
            }
        });

        $(tr).find("[data-field='box']").on("input", function() { row.box = self.flt($(this).val()); self.calculate_row(row, tr, "box"); });
        $(tr).find("[data-field='pcs']").on("input", function() { row.pcs = self.flt($(this).val()); self.calculate_row(row, tr, "pcs"); });
        $(tr).find("[data-field='ltr']").on("input", function() { row.ltr = self.flt($(this).val()); self.calculate_row(row, tr, "ltr"); });
        $(tr).find("[data-field='rate']").on("input", function() { row.rate = self.flt($(this).val()); self.calculate_row(row, tr, "rate"); });
        $(tr).find(".fe-delete-row").on("click", function() { self.delete_row(row, tr); });
    }

    calculate_row(row, tr, source) {
        const nf = row.nos_factor || 1;
        if (source === "box") {
            row.pcs = this.flt(row.box * nf);
        } else if (source === "pcs") {
            row.box = row.pcs && nf ? this.flt(row.pcs / nf) : 0;
        }
        row.qty = this.flt(row.pcs * row.ltr);
        row.amount = this.flt(row.pcs * row.rate);
        row.conversion_factor = row.ltr ? this.flt(1 / row.ltr) : 1;
        $(tr).find("[data-field='box']").val(row.box || "");
        $(tr).find("[data-field='pcs']").val(row.pcs || "");
        $(tr).find("[data-field='ltr']").val(row.ltr || "");
        $(tr).find("[data-field='qty']").val(row.qty || "");
        $(tr).find(".fe-amount-display").text(this.fmt_currency(row.amount));
        this.update_totals();
    }

    delete_row(row, tr) {
        const idx = this.items.indexOf(row);
        if (idx > -1) this.items.splice(idx, 1);
        $(tr).remove();
        this.reindex_rows();
        this.update_totals();
    }

    reindex_rows() {
        const self = this;
        this.$grid_body.find("tr").each(function(i) {
            $(this).find(".fe-col-num").text(i + 1);
            if (self.items[i]) self.items[i].idx = i + 1;
        });
        if (this.items.length === 0) this.add_empty_row();
    }

    on_item_selected(row, item_code, item_name, tr, search_uoms) {
        const self = this;
        const company = this.$company.val();
        const warehouse = this.$warehouse.val();
        frappe.call({
            method: "fast_entry_app.api.item.get_item_details",
            args: { item_code, warehouse: warehouse || "", company: company || "" },
            callback: function(r) {
                if (r.message) {
                    const d = r.message;
                    row.item_code = item_code;
                    row.item_name = d.item_name || item_name;
                    row.stock_uom = d.stock_uom;
                    row.gst_rate = d.gst_rate || 0;
                    const uoms = (search_uoms && search_uoms.length) ? search_uoms : (d.uoms || []);
                    row.nos_factor = 1;
                    row.litre_factor = 1;
                    let has_box = false;
                    if (uoms.length) {
                        const box_uom = uoms.find(u => u.uom === "Box");
                        const nos_uom = uoms.find(u => u.uom === "Nos");
                        const litre_uom = uoms.find(u => u.uom === "Litre" || u.uom === "Kg");
                        has_box = !!box_uom;
                        // Option B (piece-based stock UOM): pieces-per-box now lives on
                        // the Box row, because Nos is the stock UOM (cf 1). Legacy
                        // box-based masters still keep it on the Nos row.
                        const pack_row = (d.stock_uom === "Nos") ? (box_uom || nos_uom) : nos_uom;
                        if (pack_row) row.nos_factor = pack_row.conversion_factor || 1;
                        if (litre_uom) row.litre_factor = litre_uom.conversion_factor || 0;
                    }
                    if (!has_box && d.stock_uom === "Nos" && row.nos_factor === 1) {
                        has_box = true;
                    }
                    row.box = has_box ? 1 : 0;
                    row.pcs = has_box ? self.flt(row.box * row.nos_factor) : 1;
                    row.ltr = row.litre_factor;
                    if (!row.warehouse && warehouse) row.warehouse = warehouse;
                    else if (d.warehouse) row.warehouse = d.warehouse;
                    if (!row.rate && d.rate) { row.rate = d.rate; $(tr).find("[data-field='rate']").val(row.rate); }
                    $(tr).find(".fe-item-input").val(row.item_name).attr("data-item-code", row.item_code);
                    $(tr).find(".fe-item-code").text(row.item_code);
                    self.calculate_row(row, tr);
                    self.load_stock(row);
                }
            },
        });
    }

    search_items(query, callback) {
        frappe.call({
            method: "fast_entry_app.api.item.search_items",
            args: { search: query, company: this.$company.val() || "", limit: 15 },
            callback: function(r) { callback(r.message || []); },
        });
    }

    search_suppliers(query, callback) {
        frappe.call({
            method: "fast_entry_app.api.party.search_suppliers",
            args: { search: query, company: this.$company.val() || "", limit: 15 },
            callback: function(r) { callback(r.message || []); },
        });
    }

    bind_supplier_autocomplete() {
        const self = this;
        this.$supplier.on("input", function() {
            const val = $(this).val();
            if (val.length < 1) { self.hide_global_dropdown(); return; }
            self.search_suppliers(val, function(results) {
                let html = "";
                results.forEach(function(s) {
                    html += `<div class="fe-dropdown-item" data-value="${s.name}"><span class="fe-dd-primary">${s.supplier_name||s.name}</span><span class="fe-dd-secondary">${s.name}</span></div>`;
                });
                if (html) {
                    self.show_global_dropdown(self.$supplier, html, function($el) {
                        self.$supplier.val($el.data("value"));
                        self.on_supplier_selected($el.data("value"));
                    });
                } else {
                    self.hide_global_dropdown();
                }
            });
        });
        this.$supplier.on("keydown", function(e) {
            const $items = self.$gd.find(".fe-dropdown-item");
            const $active = $items.filter(".active");
            if (e.key === "ArrowDown") { e.preventDefault(); if (!$active.length) $items.first().addClass("active"); else { $active.removeClass("active").next().addClass("active"); } }
            else if (e.key === "ArrowUp") { e.preventDefault(); if (!$active.length) $items.last().addClass("active"); else { $active.removeClass("active").prev().addClass("active"); } }
            else if (e.key === "Enter") { e.preventDefault(); if ($active.length) $active.trigger("mousedown"); }
            else if (e.key === "Escape") { self.hide_global_dropdown(); }
        });
        this.$supplier.on("blur", function() { setTimeout(() => self.hide_global_dropdown(), 150); });
    }

    on_supplier_selected(supplier) {
        const self = this;
        frappe.call({
            method: "fast_entry_app.api.party.get_supplier_details",
            args: { supplier, company: this.$company.val() || "" },
            callback: function(r) {
                if (r.message) {
                    self.supplier_details = r.message;
                    const d = r.message;
                    const bal = d.outstanding || 0;
                    const is_unpaid = d.balance_type === "Dr";
                    const label = is_unpaid ? "Unpaid" : "Advance";
                    const cls = is_unpaid ? "fe-balance-unpaid" : "fe-balance-advance";
                    self.$supplier_balance.html('<span class="fe-balance-tag ' + cls + '">' + label + ': &#8377;' + bal.toFixed(2) + '</span>');
                    if (d.gst_type) {
                        self.$gst_type.val(d.gst_type).trigger("change");
                    }
                }
            },
        });
    }

    search_warehouses(query, callback) {
        frappe.call({
            method: "fast_entry_app.api.warehouse.search_warehouses",
            args: { search: query, company: this.$company.val() || "", limit: 15 },
            callback: function(r) { callback(r.message || []); },
        });
    }

    load_stock(row) {
        const self = this;
        const company = this.$company.val();
        if (!row.item_code || !company) return;
        // A purchase receipt belongs to exactly one company, so there is no
        // cross-company mode here by design -- an invoice cannot be raised
        // against "all companies". Cross-company stock lives in the Stock Report.
        frappe.call({
            method: "fast_entry_app.api.item.get_item_stock",
            args: { item_code: row.item_code, company: company, warehouse: row.warehouse || "" },
            callback: function(r) {
                if (!r.message) return;
                const m = r.message;
                row.wh_stock = (m.current_stock && m.current_stock.actual_qty) || 0;
                row.company_stock = m.total_actual_qty || 0;
                self.render_stock(row);
            },
        });
    }

    render_stock(row) {
        if (!row._tr) return;
        const $el = $(row._tr).find(".fe-item-stock");
        if (!$el.length) return;
        const wh = row.warehouse || this.$warehouse.val() || "-";
        $el.text("WH " + wh + ": " + this.flt(row.wh_stock) + " | Company: " + this.flt(row.company_stock));
    }

    on_warehouse_change() {
        const self = this;
        const wh = this.$warehouse.val();
        this.items.forEach(function(row) {
            if (row.item_code) {
                row.warehouse = wh || row.warehouse;
                self.load_stock(row);
            }
        });
    }

    bind_warehouse_autocomplete() {
        const self = this;
        this.$warehouse.on("input", function() {
            const val = $(this).val();
            if (val.length < 1) { self.hide_global_dropdown(); return; }
            self.search_warehouses(val, function(results) {
                let html = "";
                results.forEach(function(w) {
                    html += `<div class="fe-dropdown-item" data-value="${w.name}"><span class="fe-dd-primary">${w.warehouse_name||w.name}</span><span class="fe-dd-secondary">${w.name}</span></div>`;
                });
                if (html) {
                    self.show_global_dropdown(self.$warehouse, html, function($el) {
                        self.$warehouse.val($el.data("value"));
                        self.on_warehouse_change();
                    });
                } else {
                    self.hide_global_dropdown();
                }
            });
        });
        this.$warehouse.on("keydown", function(e) {
            const $items = self.$gd.find(".fe-dropdown-item");
            const $active = $items.filter(".active");
            if (e.key === "ArrowDown") { e.preventDefault(); if (!$active.length) $items.first().addClass("active"); else { $active.removeClass("active").next().addClass("active"); } }
            else if (e.key === "ArrowUp") { e.preventDefault(); if (!$active.length) $items.last().addClass("active"); else { $active.removeClass("active").prev().addClass("active"); } }
            else if (e.key === "Enter") { e.preventDefault(); if ($active.length) $active.trigger("mousedown"); }
            else if (e.key === "Escape") { self.hide_global_dropdown(); }
        });
        this.$warehouse.on("blur", function() { setTimeout(() => self.hide_global_dropdown(), 150); });
        this.$warehouse.on("change", function() { self.on_warehouse_change(); });
    }

    bind_keyboard() {
        const self = this;
        $(document).off("keydown.fast_entry").on("keydown.fast_entry", function(e) {
            if (!self.$root.is(":visible")) return;
            if (e.target.classList.contains("fe-global-dropdown")) return;
            const tag = e.target.tagName;
            const inInput = (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT");
            if (inInput) {
                if (e.ctrlKey && e.key === "s") { e.preventDefault(); self.save(); return; }
                if (e.ctrlKey && e.key === "p") { e.preventDefault(); self.print_last(); return; }
                if (e.key === "F2") { e.preventDefault(); self.save_and_new(); return; }
                if (e.key === "F3") { e.preventDefault(); self.add_empty_row(); return; }
                if (e.key === "Enter" && $(e.target).hasClass("fe-grid-input")) {
                    e.preventDefault();
                    const $tr = $(e.target).closest("tr");
                    const field = $(e.target).data("field");
                    if (field === "rate" || field === "ltr" || field === "pcs") {
                        const $next = $tr.next("tr");
                        if ($next.length) $next.find(".fe-item-input").focus();
                        else { self.add_empty_row(); self.$grid_body.find("tr:last .fe-item-input").focus(); }
                    }
                    return;
                }
                return;
            }
            if (e.ctrlKey && e.key === "s") { e.preventDefault(); self.save(); }
            if (e.ctrlKey && e.key === "p") { e.preventDefault(); self.print_last(); }
            if (e.key === "F2") { e.preventDefault(); self.save_and_new(); }
            if (e.key === "F3") { e.preventDefault(); self.add_empty_row(); self.$grid_body.find("tr:last .fe-item-input").focus(); }
        });
    }

    update_totals() {
        let sub_total = 0, total_box = 0, total_pcs = 0, total_ltr = 0, total_qty = 0, item_count = 0;
        this.items.forEach(row => {
            if (row.item_code) item_count++;
            total_box += this.flt(row.box);
            total_pcs += this.flt(row.pcs);
            total_ltr += this.flt(row.ltr);
            total_qty += this.flt(row.qty);
            sub_total += this.flt(row.amount);
        });

        this.$root.find("#fe-total-count").text(item_count);
        this.$root.find("#fe-total-box").text(total_box.toFixed(2));
        this.$root.find("#fe-total-pcs").text(total_pcs.toFixed(2));
        this.$root.find("#fe-total-ltr").text((total_ltr).toFixed(2));
        this.$root.find("#fe-total-qty").text((total_qty).toFixed(2));
        this.$root.find("#fe-total-amount").text(sub_total.toFixed(2));

        const discount = this.flt(this.$discount.val());
        const freight = this.flt(this.$freight.val());
        const freight_gst = freight * 0.18;
        const after_discount = sub_total - discount + freight + freight_gst;

        const tax_override = parseFloat(this.$tax_template.val()) || 0;
        const gst_type = this.$gst_type.val();
        let total_gst_rate = tax_override;
        if (!total_gst_rate) {
            this.items.forEach(row => { if (row.gst_rate > 0) total_gst_rate = row.gst_rate; });
        }

        let cgst = 0, sgst = 0, igst = 0;
        if (total_gst_rate > 0) {
            if (gst_type === "intra") {
                cgst = after_discount * (total_gst_rate / 2) / 100;
                sgst = after_discount * (total_gst_rate / 2) / 100;
            } else {
                igst = after_discount * total_gst_rate / 100;
            }
        }
        const total_tax = cgst + sgst + igst;
        const net_raw = after_discount + total_tax;
        const round_off = Math.round(net_raw) - net_raw;
        const net_total = Math.round(net_raw);

        this.$root.find("#fe-sub-total").text(sub_total.toFixed(2));
        this.$root.find("#fe-total-discount").text("-" + discount.toFixed(2));
        this.$root.find("#fe-total-freight").text("+" + freight.toFixed(2));
        this.$root.find("#fe-freight-gst").text("+" + freight_gst.toFixed(2));
        this.$root.find("#fe-cgst-amt").text(cgst.toFixed(2));
        this.$root.find("#fe-sgst-amt").text(sgst.toFixed(2));
        this.$root.find("#fe-igst-amt").text(igst.toFixed(2));
        this.$root.find("#fe-round-off").text(round_off.toFixed(2));
        this.$root.find("#fe-net-total").text(net_total.toFixed(2));

        if (freight > 0) { this.$root.find(".fe-freight-gst-row").show(); }
        else { this.$root.find(".fe-freight-gst-row").hide(); }

        if (gst_type === "intra") { this.$root.find("#fe-cgst-row, #fe-sgst-row").show(); this.$root.find("#fe-igst-row").hide(); }
        else { this.$root.find("#fe-cgst-row, #fe-sgst-row").hide(); this.$root.find("#fe-igst-row").show(); }
    }

    validate() {
        const errors = [];
        if (!this.$company.val()) errors.push("Company is required");
        if (!this.$supplier.val()) errors.push("Supplier is required");
        if (!this.$bill_no.val()) errors.push("Bill No is required");
        if (!this.$bill_date.val()) errors.push("Bill Date is required");
        const valid = this.items.filter(r => r.item_code && r.pcs > 0);
        if (!valid.length) errors.push("At least one item with PCS > 0 required");
        valid.forEach(r => { if (!r.rate || r.rate <= 0) errors.push("Row " + r.idx + ": Rate required"); });
        return errors;
    }

    get_save_data() {
        return {
            company: this.$company.val(),
            supplier: this.$supplier.val(),
            bill_no: this.$bill_no.val(),
            bill_date: this.$bill_date.val(),
            posting_date: this.$bill_date.val(),
            gst_type: this.$gst_type.val(),
            tax_override: parseFloat(this.$tax_template.val()) || 0,
            warehouse: this.$warehouse.val(),
            update_stock: this.$stock_impact.prop("checked") ? 1 : 0,
            discount: this.flt(this.$discount.val()),
            discount_pct: this.flt(this.$discount_pct.val()),
            freight: this.flt(this.$freight.val()),
            freight_gst: this.flt(this.$freight.val()) * 0.18,
            items: this.items.filter(r => r.item_code).map(r => ({
                item_code: r.item_code, item_name: r.item_name, box: r.box, pcs: r.pcs,
                ltr: r.ltr, qty: r.qty, rate: r.rate, amount: r.amount, uom: "Litre",
                stock_uom: r.stock_uom, nos_factor: r.nos_factor, litre_factor: r.litre_factor,
                conversion_factor: r.conversion_factor || 1,
                total_ltr: r.qty || 0,
                warehouse: r.warehouse, gst_rate: r.gst_rate,
            })),
        };
    }

    save(on_success) {
        const errors = this.validate();
        if (errors.length) { frappe.msgprint({title:"Validation Error", indicator:"red", message:errors.join("<br>")}); return; }
        const self = this;
        const data = this.get_save_data();
        self.$status_bar.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Saving...</span>');
        frappe.call({
            method: "fast_entry_app.api.purchase.create_purchase_invoice",
            args: { data: data },
            freeze: true,
            freeze_message: __("Creating Purchase Invoice..."),
            callback: function(r) {
                if (r.message && r.message.name) {
                    self.last_saved_name = r.message.name;
                    frappe.show_alert({ message: __("Invoice {0} saved", [r.message.name]), indicator: "green" });
                    self.$status_bar.html('<span class="fe-status-ok"><i class="fa fa-check"></i> Saved: ' + r.message.name + '</span>');
                    if (on_success) on_success();
                }
            },
            error: function() {
                self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Save failed</span>');
            },
        });
    }

    save_and_new() {
        const keep = this.$supplier.val();
        this.save(() => { this.clear_form(keep); });
    }

    clear_form(keep_supplier) {
        this.items = [];
        this.$grid_body.empty();
        this.$bill_no.val("");
        this.$bill_date.val(frappe.datetime.get_today());
        this.$discount.val(0);
        this.$discount_pct.val(0);
        this.$freight.val(0);
        this.$tax_template.val("");
        this.$stock_impact.prop("checked", true);
        if (!keep_supplier) { this.$supplier.val(""); this.$supplier_balance.text(""); this.supplier_details = {}; }
        this.add_empty_row();
        this.update_totals();
        this.$status_bar.html("");
        this.$supplier.focus();
    }

    print_last() {
        if (this.last_saved_name) window.open("/printview?doctype=Purchase Invoice&name=" + this.last_saved_name, "_blank");
        else frappe.msgprint("No invoice saved yet.");
    }

    send_whatsapp() {
        if (!this.last_saved_name) { frappe.msgprint("Save the purchase invoice first, then click WhatsApp to send it."); return; }
        this.do_wa_send();
    }

    _download_pdf(pdf_url) {
        const a = document.createElement("a");
        a.href = pdf_url;
        a.download = "";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }

    do_wa_send(number) {
        const self = this;
        const args = { purchase_invoice_name: this.last_saved_name };
        if (number) args.number = number;
        self.$status_bar.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Opening WhatsApp...</span>');
        frappe.call({
            method: "fast_entry_app.api.invoice_send.send_purchase_invoice_whatsapp",
            args: args,
            callback: function(r) {
                if (r.message && r.message.ok) {
                    self.$status_bar.html('<span class="fe-status-ok"><i class="fa fa-whatsapp"></i> Purchase Invoice ' + r.message.name + ' — PDF downloading, WhatsApp opening</span>');
                    frappe.show_alert({ message: "PDF downloading for " + r.message.name, indicator: "green" });
                    if (r.message.pdf_url) self._download_pdf(r.message.pdf_url);
                    if (r.message.wa_url) window.open(r.message.wa_url, "_blank");
                } else if (r.message && r.message.missing_field) {
                    self._prompt_missing_field(r.message, "whatsapp");
                } else {
                    self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> WhatsApp failed</span>');
                    frappe.msgprint((r.message && r.message.message) || "WhatsApp failed.");
                }
            },
            error: function(r) {
                self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> WhatsApp failed</span>');
                frappe.msgprint("WhatsApp failed.");
            },
        });
    }

    _prompt_missing_field(info, send_type) {
        const self = this;
        const is_mobile = info.missing_field === "mobile_no";
        const label = is_mobile ? "Mobile Number" : "Email Address";
        const fieldtype = is_mobile ? "Phone" : "Data";
        frappe.prompt(
            {
                fieldname: "value",
                fieldtype: fieldtype,
                label: label,
                reqd: 1,
                options: is_mobile ? "Phone" : "Email",
            },
            function(values) {
                frappe.call({
                    method: "fast_entry_app.api.invoice_send.update_party_field",
                    args: {
                        party_type: info.party_type,
                        party_name: info.party_name,
                        fieldname: info.missing_field,
                        value: values.value,
                    },
                    callback: function() {
                        frappe.show_alert({ message: label + " saved to " + info.party_name, indicator: "green" });
                        if (send_type === "whatsapp") {
                            self.do_wa_send(values.value);
                        } else {
                            self.do_email_send(values.value);
                        }
                    },
                });
            },
            __("Enter {0} for {1}", [label, info.party_name]),
            __("Save & Send")
        );
    }

    do_email_send(recipient) {
        const self = this;
        const args = { purchase_invoice_name: this.last_saved_name };
        if (recipient) args.recipient = recipient;
        self.$status_bar.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Sending email...</span>');
        frappe.call({
            method: "fast_entry_app.api.invoice_send.send_purchase_invoice_email",
            args: args,
            freeze: true,
            freeze_message: "Sending purchase invoice by email...",
            callback: function(r) {
                if (r.message && r.message.ok) {
                    self.$status_bar.html('<span class="fe-status-ok"><i class="fa fa-envelope"></i> Purchase Invoice ' + r.message.name + ' sent to ' + r.message.email + '</span>');
                    frappe.show_alert({ message: "Purchase Invoice sent to " + r.message.email, indicator: "green" });
                } else if (r.message && r.message.missing_field) {
                    self._prompt_missing_field(r.message, "email");
                } else {
                    self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Email failed</span>');
                    frappe.msgprint((r.message && r.message.message) || "Email failed.");
                }
            },
            error: function(r) {
                self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Email failed</span>');
                frappe.msgprint("Email failed.");
            },
        });
    }

    send_email() {
        if (!this.last_saved_name) { frappe.msgprint("Save the purchase invoice first, then click Email to send it."); return; }
        this.do_email_send();
    }
};
