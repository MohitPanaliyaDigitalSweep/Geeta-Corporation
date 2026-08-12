frappe.provide("fast_entry_app");

frappe.pages["fast-sales-entry"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Fast Sales Entry"),
        single_column: true,
    });
    fast_entry_app.sales_page = new fast_entry_app.SalesEntry(wrapper);
};

fast_entry_app.SalesEntry = class SalesEntry {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.items = [];
        this.settings = {};
        this.customer_details = {};
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
            console.error("Fast Sales Entry build error:", e);
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
                        <label>Customer <span class="reqd">*</span></label>
                        <div class="fe-input-wrap fe-autocomplete-wrap">
                            <input type="text" class="fe-input" id="fe-customer" placeholder="Type to search..." autocomplete="off" />
                        </div>
                        <div class="fe-party-balance" id="fe-customer-balance"></div>
                    </div>
                </div>
                <div class="fe-header-row">
                    <div class="fe-field"><label>Invoice Date <span class="reqd">*</span></label><input type="date" class="fe-input" id="fe-invoice-date" /></div>
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
                    <div class="fe-field fe-field-sm"><label>Discount</label><input type="number" class="fe-input fe-input-sm" id="fe-discount" value="0" min="0" /></div>
                    <div class="fe-field fe-field-sm"><label>Freight</label><input type="number" class="fe-input fe-input-sm" id="fe-freight" value="0" min="0" /></div>
                </div>
                <div class="fe-totals-right">
                    <table class="fe-totals-table">
                        <tr><td>Sub Total</td><td id="fe-sub-total">0.00</td></tr>
                        <tr><td>Discount</td><td id="fe-total-discount">-0.00</td></tr>
                        <tr><td>Freight</td><td id="fe-total-freight">+0.00</td></tr>
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
                    <span class="fe-shortcut-hint">F2: Save & New</span>
                    <span class="fe-shortcut-hint">F3: Add Row</span>
                </div>
                <div class="fe-actions-right">
                    <button class="fe-btn fe-btn-primary" id="fe-save"><i class="fa fa-check"></i> Save (Ctrl+S)</button>
                    <button class="fe-btn" id="fe-print-btn"><i class="fa fa-print"></i> Print (Ctrl+P)</button>
                    <button class="fe-btn fe-btn-success" id="fe-save-new"><i class="fa fa-forward"></i> Save & New (F2)</button>
                </div>
            </div>
            <div class="fe-status-bar" id="fe-status-bar"></div>
        </div>`;
    }

    bind_elements() {
        this.$grid_body = this.$root.find("#fe-grid-body");
        this.$company = this.$root.find("#fe-company");
        this.$customer = this.$root.find("#fe-customer");
        this.$customer_balance = this.$root.find("#fe-customer-balance");
        this.$invoice_date = this.$root.find("#fe-invoice-date");
        this.$gst_type = this.$root.find("#fe-gst-type");
        this.$tax_template = this.$root.find("#fe-tax-template");
        this.$warehouse = this.$root.find("#fe-warehouse");
        this.$discount = this.$root.find("#fe-discount");
        this.$freight = this.$root.find("#fe-freight");
        this.$status_bar = this.$root.find("#fe-status-bar");

        this.$invoice_date.val(frappe.datetime.get_today());
        this.load_companies();

        this.$root.find("#fe-add-row").on("click", () => this.add_empty_row());
        this.$root.find("#fe-save").on("click", () => this.save());
        this.$root.find("#fe-save-new").on("click", () => this.save_and_new());
        this.$root.find("#fe-print-btn").on("click", () => this.print_last());
        this.$discount.on("input", () => this.update_totals());
        this.$freight.on("input", () => this.update_totals());
        this.$tax_template.on("change", () => this.update_totals());
        this.$gst_type.on("change", () => this.update_totals());

        this.bind_customer_autocomplete();
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
        const row = { idx, item_code:"", item_name:"", box:0, pcs:0, ltr:0, qty:0, rate:0, amount:0, uom:"", nos_factor:1, litre_factor:1, stock_uom:"", warehouse:"", gst_rate:0 };
        this.items.push(row);
        this.render_row(row);
    }

    render_row(row) {
        const tr = document.createElement("tr");
        tr.dataset.idx = row.idx;
        tr.className = "fe-grid-row";
        tr.innerHTML = `
            <td class="fe-col-num">${row.idx}</td>
            <td class="fe-col-item">
                <div class="fe-input-wrap fe-autocomplete-wrap">
                    <input type="text" class="fe-grid-input fe-item-input" data-field="item_code" value="${row.item_name||row.item_code}" placeholder="Search..." autocomplete="off" />
                </div>
                <div class="fe-item-code">${row.item_code||""}</div>
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
        const lf = row.litre_factor || 1;
        if (source === "ltr") {
            row.qty = row.ltr;
            row.pcs = row.qty && lf ? this.flt(row.qty / (lf / nf)) : 0;
            row.box = row.pcs && nf ? this.flt(row.pcs / nf) : 0;
        } else if (source === "pcs") {
            row.pcs = this.flt(row.pcs);
            row.box = row.pcs && nf ? this.flt(row.pcs / nf) : 0;
            row.ltr = this.flt(lf / nf);
            row.qty = this.flt(row.pcs * (lf / nf));
        } else {
            row.pcs = this.flt(row.box * nf);
            row.ltr = this.flt(lf / nf);
            row.qty = this.flt(row.box * lf);
        }
        row.amount = this.flt(row.pcs * row.rate);
        row.conversion_factor = lf ? this.flt(1 / lf) : 1;
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
                    if (uoms.length) {
                        const nos_uom = uoms.find(u => u.uom === "Nos");
                        const litre_uom = uoms.find(u => u.uom === "Litre" || u.uom === "Kg");
                        if (nos_uom) row.nos_factor = nos_uom.conversion_factor || 1;
                        if (litre_uom) row.litre_factor = litre_uom.conversion_factor || 1;
                    }
                    if (!row.warehouse && warehouse) row.warehouse = warehouse;
                    else if (d.warehouse) row.warehouse = d.warehouse;
                    if (!row.rate && d.rate) { row.rate = d.rate; $(tr).find("[data-field='rate']").val(row.rate); }
                    $(tr).find(".fe-item-input").val(row.item_name).attr("data-item-code", row.item_code);
                    $(tr).find(".fe-item-code").text(row.item_code);
                    self.calculate_row(row, tr);
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

    search_customers(query, callback) {
        frappe.call({
            method: "fast_entry_app.api.party.search_customers",
            args: { search: query, company: this.$company.val() || "", limit: 15 },
            callback: function(r) { callback(r.message || []); },
        });
    }

    bind_customer_autocomplete() {
        const self = this;
        this.$customer.on("input", function() {
            const val = $(this).val();
            if (val.length < 1) { self.hide_global_dropdown(); return; }
            self.search_customers(val, function(results) {
                let html = "";
                results.forEach(function(c) {
                    html += `<div class="fe-dropdown-item" data-value="${c.name}"><span class="fe-dd-primary">${c.customer_name||c.name}</span><span class="fe-dd-secondary">${c.name}</span></div>`;
                });
                if (html) {
                    self.show_global_dropdown(self.$customer, html, function($el) {
                        self.$customer.val($el.data("value"));
                        self.on_customer_selected($el.data("value"));
                    });
                } else {
                    self.hide_global_dropdown();
                }
            });
        });
        this.$customer.on("keydown", function(e) {
            const $items = self.$gd.find(".fe-dropdown-item");
            const $active = $items.filter(".active");
            if (e.key === "ArrowDown") { e.preventDefault(); if (!$active.length) $items.first().addClass("active"); else { $active.removeClass("active").next().addClass("active"); } }
            else if (e.key === "ArrowUp") { e.preventDefault(); if (!$active.length) $items.last().addClass("active"); else { $active.removeClass("active").prev().addClass("active"); } }
            else if (e.key === "Enter") { e.preventDefault(); if ($active.length) $active.trigger("mousedown"); }
            else if (e.key === "Escape") { self.hide_global_dropdown(); }
        });
        this.$customer.on("blur", function() { setTimeout(() => self.hide_global_dropdown(), 150); });
    }

    on_customer_selected(customer) {
        const self = this;
        frappe.call({
            method: "fast_entry_app.api.party.get_customer_details",
            args: { customer, company: this.$company.val() || "" },
            callback: function(r) {
                if (r.message) {
                    self.customer_details = r.message;
                    const d = r.message;
                    const bal = d.outstanding || 0;
                    const sign = d.balance_type === "Dr" ? " Dr" : " Cr";
                    self.$customer_balance.text("Balance: " + (bal).toFixed(2) + sign);
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
    }

    bind_keyboard() {
        const self = this;
        $(document).off("keydown.fast_entry_sales").on("keydown.fast_entry_sales", function(e) {
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
        this.$root.find("#fe-total-box").text(total_box || 0);
        this.$root.find("#fe-total-pcs").text(total_pcs || 0);
        this.$root.find("#fe-total-ltr").text((total_ltr).toFixed(2));
        this.$root.find("#fe-total-qty").text((total_qty).toFixed(2));
        this.$root.find("#fe-total-amount").text(sub_total.toFixed(2));

        const discount = this.flt(this.$discount.val());
        const freight = this.flt(this.$freight.val());
        const after_discount = sub_total - discount + freight;

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
        this.$root.find("#fe-cgst-amt").text(cgst.toFixed(2));
        this.$root.find("#fe-sgst-amt").text(sgst.toFixed(2));
        this.$root.find("#fe-igst-amt").text(igst.toFixed(2));
        this.$root.find("#fe-round-off").text(round_off.toFixed(2));
        this.$root.find("#fe-net-total").text(net_total.toFixed(2));

        if (gst_type === "intra") { this.$root.find("#fe-cgst-row, #fe-sgst-row").show(); this.$root.find("#fe-igst-row").hide(); }
        else { this.$root.find("#fe-cgst-row, #fe-sgst-row").hide(); this.$root.find("#fe-igst-row").show(); }
    }

    validate() {
        const errors = [];
        if (!this.$company.val()) errors.push("Company is required");
        if (!this.$customer.val()) errors.push("Customer is required");
        if (!this.$invoice_date.val()) errors.push("Invoice Date is required");
        const valid = this.items.filter(r => r.item_code && r.pcs > 0);
        if (!valid.length) errors.push("At least one item with PCS > 0 required");
        valid.forEach(r => { if (!r.rate || r.rate <= 0) errors.push("Row " + r.idx + ": Rate required"); });
        return errors;
    }

    get_save_data() {
        return {
            company: this.$company.val(),
            customer: this.$customer.val(),
            invoice_date: this.$invoice_date.val(),
            posting_date: this.$invoice_date.val(),
            gst_type: this.$gst_type.val(),
            tax_override: parseFloat(this.$tax_template.val()) || 0,
            warehouse: this.$warehouse.val(),
            discount: this.flt(this.$discount.val()),
            freight: this.flt(this.$freight.val()),
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

    save() {
        const errors = this.validate();
        if (errors.length) { frappe.msgprint({title:"Validation Error", indicator:"red", message:errors.join("<br>")}); return; }
        const self = this;
        const data = this.get_save_data();
        self.$status_bar.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Saving...</span>');
        frappe.call({
            method: "fast_entry_app.api.sales.create_sales_invoice",
            args: { data: data },
            freeze: true,
            freeze_message: __("Creating Sales Invoice..."),
            callback: function(r) {
                if (r.message && r.message.name) {
                    self.last_saved_name = r.message.name;
                    frappe.show_alert({ message: __("Invoice {0} saved", [r.message.name]), indicator: "green" });
                    self.$status_bar.html('<span class="fe-status-ok"><i class="fa fa-check"></i> Saved: ' + r.message.name + '</span>');
                }
            },
            error: function() {
                self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Save failed</span>');
            },
        });
    }

    save_and_new() {
        const keep = this.$customer.val();
        this.save();
        setTimeout(() => { this.clear_form(keep); }, 1500);
    }

    clear_form(keep_customer) {
        this.items = [];
        this.$grid_body.empty();
        this.$invoice_date.val(frappe.datetime.get_today());
        this.$discount.val(0);
        this.$freight.val(0);
        this.$tax_template.val("");
        if (!keep_customer) { this.$customer.val(""); this.$customer_balance.text(""); this.customer_details = {}; }
        this.add_empty_row();
        this.update_totals();
        this.$status_bar.html("");
        this.$customer.focus();
    }

    print_last() {
        if (this.last_saved_name) window.open("/printview?doctype=Sales Invoice&name=" + this.last_saved_name, "_blank");
        else frappe.msgprint("No invoice saved yet.");
    }
};
