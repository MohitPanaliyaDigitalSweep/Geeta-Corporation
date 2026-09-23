frappe.provide("fast_entry_app");

frappe.pages["fast-ict-entry"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Fast Inter Company Transfer"), single_column: true });
    fast_entry_app.ict_page = new fast_entry_app.ICTEntry(wrapper);
};

fast_entry_app.ICTEntry = class ICTEntry {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.items = [];
        this.last_saved_name = null;
        this.active_input = null;
        this.build_global_dropdown();
        this.build();
    }

    flt(v) { return parseFloat(v) || 0; }
    fmt(v) { return (v || 0).toFixed(2); }

    build_global_dropdown() {
        this.$gd = $('<div class="fe-global-dropdown"></div>').appendTo("body");
        this.$gd.on("mousedown", ".fe-dropdown-item", (e) => {
            e.preventDefault();
            if (this._dropdown_select_handler) this._dropdown_select_handler($(e.currentTarget));
            this.hide_global_dropdown();
        });
        $(document).on("mousedown", (e) => {
            if (!$(e.target).closest(".fe-global-dropdown, .fe-input, .fe-grid-input").length) this.hide_global_dropdown();
        });
    }

    show_global_dropdown($input, items_html, select_handler) {
        this._dropdown_select_handler = select_handler;
        this.$gd.html(items_html).show();
        const rect = $input[0].getBoundingClientRect();
        this.$gd.css({ top: rect.bottom + 1, left: rect.left, width: Math.max(rect.width, 250) });
        this.active_input = $input;
    }

    hide_global_dropdown() { this.$gd.hide().empty(); this.active_input = null; }

    build() {
        this.$root = $(this.wrapper.page.main);
        this.$root.html(this.get_html());
        this.bind_elements();
        this.add_empty_row();
        this.bind_keyboard();
        this.update_totals();
    }

    get_html() {
        return `<div class="fast-entry-container">
            <div class="fe-header-section">
                <div class="fe-header-row">
                    <div class="fe-field"><label>Source Company <span class="reqd">*</span></label><select class="fe-input" id="fe-source-company"></select></div>
                    <div class="fe-field"><label>Target Company <span class="reqd">*</span></label><select class="fe-input" id="fe-target-company"></select></div>
                    <div class="fe-field"><label>Posting Date <span class="reqd">*</span></label><input type="date" class="fe-input" id="fe-posting-date" /></div>
                    <div class="fe-field"><label>GST Type</label>
                        <select class="fe-input" id="fe-gst-type">
                            <option value="inter">Inter-State (IGST)</option>
                            <option value="intra">Intra-State (CGST+SGST)</option>
                        </select>
                    </div>
                </div>
                <div class="fe-header-row">
                    <div class="fe-field"><label>Sales Tax Template</label><select class="fe-input" id="fe-sales-tax-template"><option value="">Auto (Company Default)</option></select></div>
                    <div class="fe-field"><label>Purchase Tax Template</label><select class="fe-input" id="fe-purchase-tax-template"><option value="">Auto (Company Default)</option></select></div>
                </div>
            </div>
            <div class="fe-grid-section">
                <div class="fe-grid-header">
                    <span class="fe-grid-title"><i class="fa fa-exchange"></i> Items to Transfer</span>
                    <span class="fe-grid-subtitle">Source Company → Target Company</span>
                </div>
                <div class="fe-grid-wrap">
                    <table class="fe-grid" id="fe-items-grid">
                        <thead><tr>
                            <th class="fe-col-num">#</th>
                            <th class="fe-col-item">Item</th>
                            <th class="fe-col-src-wh">Source Warehouse</th>
                            <th class="fe-col-tgt-wh">Target Warehouse</th>
                            <th class="fe-col-box">Box</th>
                            <th class="fe-col-pcs">PCS</th>
                            <th class="fe-col-ltr">LTR</th>
                            <th class="fe-col-qty">Total Litre</th>
                            <th class="fe-col-rate">Rate</th>
                            <th class="fe-col-amount">Amount</th>
                            <th class="fe-col-action"></th>
                        </tr></thead>
                        <tbody id="fe-grid-body"></tbody>
                        <tfoot><tr class="fe-grid-total-row">
                            <td colspan="4" style="text-align:center;font-weight:700;"><span id="fe-total-count">0</span> Items</td>
                            <td class="fe-col-box" id="fe-total-box">0</td>
                            <td class="fe-col-pcs" id="fe-total-pcs">0</td>
                            <td class="fe-col-ltr" id="fe-total-ltr">0.00</td>
                            <td class="fe-col-qty" id="fe-total-qty">0.00</td>
                            <td class="fe-col-rate"></td>
                            <td class="fe-col-amount" id="fe-total-amount">0.00</td>
                            <td class="fe-col-action"></td>
                        </tr></tfoot>
                    </table>
                </div>
                <div class="fe-grid-toolbar">
                    <button class="fe-btn fe-btn-sm" id="fe-add-row" title="Add Row (F3)"><i class="fa fa-plus"></i> Add Row</button>
                </div>
            </div>
            <div class="fe-totals-section">
                <div class="fe-totals-left"><div class="fe-field fe-field-sm"><label>Remarks</label><input type="text" class="fe-input fe-input-sm" id="fe-remarks" placeholder="Optional" /></div></div>
                <div class="fe-totals-right">
                    <table class="fe-totals-table">
                        <tr><td>Total Box</td><td id="fe-total-box-display">0</td></tr>
                        <tr><td>Total Qty (PCS)</td><td id="fe-total-pcs-display">0</td></tr>
                        <tr><td>Total Ltr</td><td id="fe-total-qty-display">0.00</td></tr>
                        <tr><td>Net Total (INR)</td><td id="fe-net-total-display">0.00</td></tr>
                        <tr><td>Tax</td><td id="fe-tax-total-display">0.00</td></tr>
                        <tr class="fe-net-total"><td><b>Grand Total</b></td><td><b id="fe-grand-total">0.00</b></td></tr>
                    </table>
                </div>
            </div>
            <div class="fe-actions-section">
                <div class="fe-actions-left">
                    <span class="fe-shortcut-hint">Ctrl+S: Save</span>
                    <span class="fe-shortcut-hint">F2: Save & New</span>
                    <span class="fe-shortcut-hint">F3: Add Row</span>
                </div>
                <div class="fe-actions-right">
                    <button class="fe-btn fe-btn-primary" id="fe-save"><i class="fa fa-check"></i> Save (Ctrl+S)</button>
                    <button class="fe-btn fe-btn-success" id="fe-save-new"><i class="fa fa-forward"></i> Save & New (F2)</button>
                </div>
            </div>
            <div class="fe-tax-preview-section" id="fe-tax-preview-section">
                <div class="fe-tax-preview-card">
                    <div class="fe-tax-preview-header">
                        <i class="fa fa-calculator"></i> Tax Preview
                        <span class="fe-tax-preview-subtitle" id="fe-tax-preview-subtitle"></span>
                    </div>
                    <div class="fe-tax-preview-body" id="fe-tax-preview-body">
                        <div class="fe-tax-empty">Select a tax template to see tax breakdown</div>
                    </div>
                </div>
            </div>
            <div class="fe-status-bar" id="fe-status-bar"></div>
            <div id="fe-ict-section" style="display:none;">
                <div id="fe-progress-section"></div>
                <div id="fe-docs-section"></div>
                <div id="fe-stock-section"></div>
                <div id="fe-payment-section"></div>
            </div>
        </div>`;
    }

    bind_elements() {
        this.$grid_body = this.$root.find("#fe-grid-body");
        this.$source_company = this.$root.find("#fe-source-company");
        this.$target_company = this.$root.find("#fe-target-company");
        this.$posting_date = this.$root.find("#fe-posting-date");
        this.$gst_type = this.$root.find("#fe-gst-type");
        this.$sales_tax_template = this.$root.find("#fe-sales-tax-template");
        this.$purchase_tax_template = this.$root.find("#fe-purchase-tax-template");
        this.$remarks = this.$root.find("#fe-remarks");
        this.$status_bar = this.$root.find("#fe-status-bar");
        this.$tax_preview_body = this.$root.find("#fe-tax-preview-body");
        this.$tax_preview_subtitle = this.$root.find("#fe-tax-preview-subtitle");
        this.$posting_date.val(frappe.datetime.get_today());
        this.tax_templates = { sales: [], purchase: [] };
        this.load_companies();
        this.load_tax_templates();
        this.$root.find("#fe-add-row").on("click", () => this.add_empty_row());
        this.$root.find("#fe-save").on("click", () => this.save());
        this.$root.find("#fe-save-new").on("click", () => this.save_and_new());
        this.$source_company.on("change", () => { localStorage.setItem("fe_ict_source_company", this.$source_company.val()); this.update_tax_preview(); });
        this.$target_company.on("change", () => { localStorage.setItem("fe_ict_target_company", this.$target_company.val()); this.update_tax_preview(); });
        this.$sales_tax_template.on("change", () => this.update_tax_preview());
        this.$purchase_tax_template.on("change", () => this.update_tax_preview());
    }

    load_companies() {
        const self = this;
        frappe.call({ method: "frappe.client.get_list", args: { doctype: "Company", filters: {}, fields: ["name"], limit_page_length: 100 },
            callback: function(r) {
                const companies = r.message || [];
                self.$source_company.empty().append('<option value="">Select Source</option>');
                self.$target_company.empty().append('<option value="">Select Target</option>');
                companies.forEach(c => { self.$source_company.append(`<option value="${c.name}">${c.name}</option>`); self.$target_company.append(`<option value="${c.name}">${c.name}</option>`); });
                var ls = localStorage.getItem("fe_ict_source_company"), lt = localStorage.getItem("fe_ict_target_company");
                if (ls && companies.find(c => c.name === ls)) self.$source_company.val(ls);
                if (lt && companies.find(c => c.name === lt)) self.$target_company.val(lt);
            }
        });
    }

    load_tax_templates() {
        const self = this;
        frappe.call({ method: "fast_entry_app.api.ict.get_tax_templates_with_details", args: {},
            callback: function(r) {
                const data = r.message || { sales: [], purchase: [] };
                self.tax_templates = data;

                self.$sales_tax_template.empty().append('<option value="">Auto (Company Default)</option>');
                data.sales.forEach(t => {
                    const rates = t.taxes.map(tx => tx.rate + "%").join("+");
                    const label = rates ? `${t.name} (${rates})` : t.name;
                    self.$sales_tax_template.append(`<option value="${t.name}">${label}</option>`);
                });

                self.$purchase_tax_template.empty().append('<option value="">Auto (Company Default)</option>');
                data.purchase.forEach(t => {
                    const rates = t.taxes.map(tx => tx.rate + "%").join("+");
                    const label = rates ? `${t.name} (${rates})` : t.name;
                    self.$purchase_tax_template.append(`<option value="${t.name}">${label}</option>`);
                });
            }
        });
    }

    add_empty_row() {
        const idx = this.items.length + 1;
        const row = { idx, item_code:"", item_name:"", box:0, pcs:0, ltr:0, qty:0, uom:"Nos", rate:0, amount:0, source_warehouse:"", target_warehouse:"", nos_factor:1, litre_factor:0, stock_uom:"" };
        this.items.push(row);
        this.render_row(row);
    }

    render_row(row) {
        const tr = document.createElement("tr");
        tr.dataset.idx = row.idx; tr.className = "fe-grid-row";
        tr.innerHTML = `<td class="fe-col-num">${row.idx}</td>
            <td class="fe-col-item"><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-grid-input fe-item-input" data-field="item_code" value="${row.item_name||row.item_code}" placeholder="Search item..." autocomplete="off" /></div><div class="fe-item-code">${row.item_code||""}</div><div class="fe-item-stock" style="display:none;"></div></td>
            <td class="fe-col-src-wh"><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-grid-input fe-wh-input" data-field="source_warehouse" value="${row.source_warehouse}" placeholder="Source WH" autocomplete="off" /></div></td>
            <td class="fe-col-tgt-wh"><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-grid-input fe-wh-input" data-field="target_warehouse" value="${row.target_warehouse}" placeholder="Target WH" autocomplete="off" /></div></td>
            <td class="fe-col-box"><input type="number" class="fe-grid-input fe-num-input" data-field="box" value="${row.box||""}" min="0" step="1" /></td>
            <td class="fe-col-pcs"><input type="number" class="fe-grid-input fe-num-input" data-field="pcs" value="${row.pcs||""}" min="0" /></td>
            <td class="fe-col-ltr"><input type="number" class="fe-grid-input fe-num-input" data-field="ltr" value="${row.ltr||""}" min="0" step="0.01" /></td>
            <td class="fe-col-qty"><input type="number" class="fe-grid-input fe-num-input" data-field="qty" value="${row.qty||""}" min="0" readonly /></td>
            <td class="fe-col-rate"><input type="number" class="fe-grid-input fe-num-input" data-field="rate" value="${row.rate||""}" min="0" step="0.01" /></td>
            <td class="fe-col-amount"><span class="fe-amount-display">${this.fmt(row.amount)}</span></td>
            <td class="fe-col-action"><button class="fe-btn-icon fe-delete-row" title="Delete"><i class="fa fa-times"></i></button></td>`;
        this.$grid_body[0].appendChild(tr);
        this.bind_row_events(tr, row);
    }

    bind_row_events(tr, row) {
        const self = this;
        const $item_input = $(tr).find(".fe-item-input");
        $item_input.on("input", function() {
            const val = $(this).val(), $inp = $(this);
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
                } else { self.hide_global_dropdown(); }
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
            } else if (e.key === "ArrowUp") {
                e.preventDefault();
                if (!$active.length) $items.last().addClass("active");
                else { $active.removeClass("active").prev().addClass("active"); }
            } else if (e.key === "Enter") {
                e.preventDefault();
                if ($active.length) $active.trigger("mousedown");
            } else if (e.key === "Escape") { self.hide_global_dropdown(); }
        });
        $(tr).find("[data-field='box']").on("input", function() { row.box = self.flt($(this).val()); self.calculate_row(row, tr, "box"); });
        $(tr).find("[data-field='pcs']").on("input", function() { row.pcs = self.flt($(this).val()); self.calculate_row(row, tr, "pcs"); });
        $(tr).find("[data-field='ltr']").on("input", function() { row.ltr = self.flt($(this).val()); self.calculate_row(row, tr, "ltr"); });
        $(tr).find("[data-field='rate']").on("input", function() { row.rate = self.flt($(this).val()); self.calculate_row(row, tr, "rate"); });
        $(tr).find(".fe-delete-row").on("click", function() { self.delete_row(row, tr); });
        this.bind_wh_autocomplete($(tr).find("[data-field='source_warehouse']"), row, "source_warehouse");
        this.bind_wh_autocomplete($(tr).find("[data-field='target_warehouse']"), row, "target_warehouse");
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
        $(tr).find(".fe-amount-display").text(this.fmt(row.amount));
        this.update_totals();
    }

    delete_row(row, tr) { const idx = this.items.indexOf(row); if (idx > -1) this.items.splice(idx, 1); $(tr).remove(); this.reindex_rows(); this.update_totals(); }

    reindex_rows() { const self = this; this.$grid_body.find("tr").each(function(i) { $(this).find(".fe-col-num").text(i + 1); if (self.items[i]) self.items[i].idx = i + 1; }); if (this.items.length === 0) this.add_empty_row(); }

    on_item_selected(row, item_code, item_name, tr, search_uoms) {
        const self = this;
        row.item_code = item_code; row.item_name = item_name;
        $(tr).find(".fe-item-input").val(row.item_name).attr("data-item-code", row.item_code);
        $(tr).find(".fe-item-code").text(row.item_code);
        frappe.call({
            method: "fast_entry_app.api.item.get_item_uom",
            args: { item_code: item_code },
            callback: function(r) {
                if (r.message) {
                    const d = r.message;
                    row.nos_factor = d.nos_factor || 1;
                    row.litre_factor = d.litre_factor || 0;
                    row.ltr = row.litre_factor;
                    row.stock_uom = d.stock_uom || "Nos";
                    row.uom = d.stock_uom || "Nos";
                    self.calculate_row(row, tr);
                }
            }
        });
        this.show_item_stock(row, tr);
    }

    show_item_stock(row, tr) {
        const self = this;
        const src_company = this.$source_company.val();
        const tgt_company = this.$target_company.val();
        if (!row.item_code) return;

        const $stock = $(tr).find(".fe-item-stock");
        if (!src_company && !tgt_company) { $stock.hide(); return; }

        let pending = 0;
        const results = {};

        function render() {
            if (pending > 0) return;
            let html = '';
            if (results.src) {
                const src_wh = row.source_warehouse || "";
                const src_name = src_wh ? src_wh.split(" - ")[0] : "Source";
                const qty = results.src.actual_qty || 0;
                const color = qty > 0 ? '#059669' : qty < 0 ? '#dc2626' : '#9ca3af';
                html += '<span style="color:#6b7280;font-size:9px;">SRC:</span> <span style="color:'+color+';font-weight:600;">'+src_name+': '+self.fmt(qty)+'</span>';
            }
            if (results.tgt) {
                const tgt_wh = row.target_warehouse || "";
                const tgt_name = tgt_wh ? tgt_wh.split(" - ")[0] : "Target";
                const qty = results.tgt.actual_qty || 0;
                const color = qty > 0 ? '#3b82f6' : qty < 0 ? '#dc2626' : '#9ca3af';
                html += '<span style="color:#6b7280;font-size:9px;margin-left:8px;">TGT:</span> <span style="color:'+color+';font-weight:600;">'+tgt_name+': '+self.fmt(qty)+'</span>';
            }
            if (html) { $stock.html(html).show(); } else { $stock.hide(); }
        }

        if (src_company && row.source_warehouse) {
            pending++;
            frappe.call({
                method: "fast_entry_app.api.item.get_item_stock",
                args: { item_code: row.item_code, company: src_company, warehouse: row.source_warehouse },
                callback: function(r) { results.src = r.message ? (r.message.current_stock || {}) : {}; pending--; render(); },
                error: function() { pending--; render(); }
            });
        }
        if (tgt_company && row.target_warehouse) {
            pending++;
            frappe.call({
                method: "fast_entry_app.api.item.get_item_stock",
                args: { item_code: row.item_code, company: tgt_company, warehouse: row.target_warehouse },
                callback: function(r) { results.tgt = r.message ? (r.message.current_stock || {}) : {}; pending--; render(); },
                error: function() { pending--; render(); }
            });
        }

        if (pending === 0) render();
    }

    search_items(query, callback) { frappe.call({ method: "fast_entry_app.api.item.search_items", args: { search: query, company: this.$source_company.val() || "", limit: 15 }, callback: function(r) { callback(r.message || []); } }); }

    bind_wh_autocomplete($input, row, field) {
        const self = this;
        $input.on("input", function() {
            const val = $(this).val(); if (val.length < 1) { self.hide_global_dropdown(); return; }
            const company = field === "source_warehouse" ? self.$source_company.val() : self.$target_company.val();
            frappe.call({ method: "fast_entry_app.api.warehouse.search_warehouses", args: { search: val, company: company || "", limit: 15 },
                callback: function(r) { let html = ""; (r.message || []).forEach(function(w) { html += `<div class="fe-dropdown-item" data-value="${w.name}"><span class="fe-dd-primary">${w.warehouse_name||w.name}</span><span class="fe-dd-secondary">${w.name}</span></div>`; });
                    if (html) { self.show_global_dropdown($input, html, function($el) { $input.val($el.data("value")); row[field] = $el.data("value"); }); } else { self.hide_global_dropdown(); } }
            });
        });
        $input.on("keydown", function(e) {
            const $items = self.$gd.find(".fe-dropdown-item");
            const $active = $items.filter(".active");
            if (e.key === "ArrowDown") { e.preventDefault(); if (!$active.length) $items.first().addClass("active"); else { $active.removeClass("active").next().addClass("active"); } }
            else if (e.key === "ArrowUp") { e.preventDefault(); if (!$active.length) $items.last().addClass("active"); else { $active.removeClass("active").prev().addClass("active"); } }
            else if (e.key === "Enter") { e.preventDefault(); if ($active.length) $active.trigger("mousedown"); }
            else if (e.key === "Escape") { self.hide_global_dropdown(); }
        }); $input.on("blur", function() { setTimeout(() => self.hide_global_dropdown(), 150); });
    }

    bind_keyboard() {
        const self = this;
        $(document).off("keydown.fast_ict_entry").on("keydown.fast_ict_entry", function(e) {
            if (!self.$root.is(":visible")) return;
            if (e.target.classList.contains("fe-global-dropdown")) return;
            const tag = e.target.tagName, inInput = (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT");
            if (inInput) { if (e.ctrlKey && e.key === "s") { e.preventDefault(); self.save(); return; } if (e.key === "F2") { e.preventDefault(); self.save_and_new(); return; } if (e.key === "F3") { e.preventDefault(); self.add_empty_row(); return; }
                if (e.key === "Enter" && $(e.target).hasClass("fe-grid-input")) { e.preventDefault(); const $tr = $(e.target).closest("tr"), field = $(e.target).data("field"); if (field === "rate" || field === "ltr" || field === "pcs") { const $next = $tr.next("tr"); if ($next.length) $next.find(".fe-item-input").focus(); else { self.add_empty_row(); self.$grid_body.find("tr:last .fe-item-input").focus(); } } return; } return; }
            if (e.ctrlKey && e.key === "s") { e.preventDefault(); self.save(); } if (e.key === "F2") { e.preventDefault(); self.save_and_new(); } if (e.key === "F3") { e.preventDefault(); self.add_empty_row(); self.$grid_body.find("tr:last .fe-item-input").focus(); }
        });
    }

    update_totals() {
        let total_box = 0, total_pcs = 0, total_ltr = 0, total_amount = 0, item_count = 0;
        this.items.forEach(row => {
            if (row.item_code) item_count++;
            total_box += this.flt(row.box);
            total_pcs += this.flt(row.pcs);
            total_ltr += this.flt(row.ltr);
            total_amount += this.flt(row.pcs) * this.flt(row.rate);
        });
        this.$root.find("#fe-total-count").text(item_count);
        this.$root.find("#fe-total-box").text(total_box.toFixed(2));
        this.$root.find("#fe-total-pcs").text(total_pcs.toFixed(2));
        this.$root.find("#fe-total-ltr").text(total_ltr.toFixed(2));
        this.$root.find("#fe-total-qty").text(total_pcs.toFixed(2));
        this.$root.find("#fe-total-amount").text(total_amount.toFixed(2));
        this.$root.find("#fe-total-box-display").text(total_box.toFixed(2));
        this.$root.find("#fe-total-pcs-display").text(total_pcs.toFixed(0));
        this.$root.find("#fe-total-qty-display").text(total_ltr.toFixed(2));
        this.update_tax_preview();
    }

    update_tax_preview() {
        const self = this;
        const items = this.items.filter(r => r.item_code).map(r => ({
            item_code: r.item_code, pcs: r.pcs, rate: r.rate, amount: r.amount
        }));

        const sales_template = this.$sales_tax_template.val() || "";
        const purchase_template = this.$purchase_tax_template.val() || "";

        if (!sales_template && !purchase_template) {
            const net_total = items.reduce((s, r) => s + this.flt(r.amount), 0);
            this.$root.find("#fe-net-total-display").text(net_total.toFixed(2));
            this.$root.find("#fe-tax-total-display").text("0.00");
            this.$root.find("#fe-grand-total").text(net_total.toFixed(2));
            this.$tax_preview_body.html('<div class="fe-tax-empty">Select a tax template to see tax breakdown</div>');
            this.$tax_preview_subtitle.text("");
            return;
        }

        let pending = 0;
        const results = {};

        function render() {
            if (pending > 0) return;
            self.render_tax_preview_body(results.sales, results.purchase, items);
        }

        if (sales_template) {
            pending++;
            frappe.call({
                method: "fast_entry_app.api.ict.calculate_tax_preview",
                args: { items_json: JSON.stringify(items), template_name: sales_template, tax_type: "sales" },
                callback: function(r) { results.sales = r.message; pending--; render(); },
                error: function() { pending--; render(); }
            });
        }
        if (purchase_template) {
            pending++;
            frappe.call({
                method: "fast_entry_app.api.ict.calculate_tax_preview",
                args: { items_json: JSON.stringify(items), template_name: purchase_template, tax_type: "purchase" },
                callback: function(r) { results.purchase = r.message; pending--; render(); },
                error: function() { pending--; render(); }
            });
        }
    }

    render_tax_preview_body(sales_result, purchase_result, items) {
        const net_total = items.reduce((s, r) => s + this.flt(r.amount), 0);
        let total_tax = 0;
        let html = '';

        if (sales_result) {
            html += this.build_tax_table("Sales (Source)", sales_result);
            total_tax += sales_result.total_tax || 0;
        }
        if (purchase_result) {
            html += this.build_tax_table("Purchase (Target)", purchase_result);
            total_tax += purchase_result.total_tax || 0;
        }

        if (!html) {
            html = '<div class="fe-tax-empty">No tax rows in selected templates</div>';
        }

        this.$tax_preview_body.html(html);
        this.$root.find("#fe-net-total-display").text(net_total.toFixed(2));
        this.$root.find("#fe-tax-total-display").text(total_tax.toFixed(2));
        this.$root.find("#fe-grand-total").text((net_total + total_tax).toFixed(2));

        const parts = [];
        if (sales_result) parts.push("Sales: " + (sales_result.tax_rows.length) + " rows");
        if (purchase_result) parts.push("Purchase: " + (purchase_result.tax_rows.length) + " rows");
        this.$tax_preview_subtitle.text(parts.join(" | "));
    }

    build_tax_table(label, result) {
        let h = `<div class="fe-tax-table-wrap">`;
        h += `<div class="fe-tax-table-label">${label}</div>`;
        h += `<table class="fe-tax-table">`;
        h += `<thead><tr><th>Account</th><th>Rate</th><th style="text-align:right;">Amount</th></tr></thead><tbody>`;
        if (result.tax_rows && result.tax_rows.length) {
            result.tax_rows.forEach(row => {
                h += `<tr>`;
                h += `<td>${row.account_head || ""}</td>`;
                h += `<td>${row.rate ? row.rate + "%" : (row.charge_type === "Actual" ? "Actual" : "")}</td>`;
                h += `<td style="text-align:right;font-weight:600;">${this.fmt(row.amount)}</td>`;
                h += `</tr>`;
            });
            h += `<tr class="fe-tax-total"><td><b>Total Tax</b></td><td></td><td style="text-align:right;"><b>${this.fmt(result.total_tax)}</b></td></tr>`;
        } else {
            h += `<tr><td colspan="3" style="text-align:center;color:#9ca3af;">No tax rows</td></tr>`;
        }
        h += `</tbody></table></div>`;
        return h;
    }

    validate() {
        const errors = [];
        if (!this.$source_company.val()) errors.push("Source Company is required");
        if (!this.$target_company.val()) errors.push("Target Company is required");
        if (this.$source_company.val() && this.$target_company.val() && this.$source_company.val() === this.$target_company.val()) errors.push("Source and Target cannot be same");
        if (!this.$posting_date.val()) errors.push("Posting Date is required");
        const valid = this.items.filter(r => r.item_code && r.pcs > 0);
        if (!valid.length) errors.push("At least one item with PCS > 0 required");
        valid.forEach(r => { if (!r.rate || r.rate <= 0) errors.push("Row " + r.idx + ": Rate required"); if (!r.source_warehouse) errors.push("Row " + r.idx + ": Source WH required"); if (!r.target_warehouse) errors.push("Row " + r.idx + ": Target WH required"); });
        return errors;
    }

    get_save_data() {
        return { company: this.$source_company.val(), to_company: this.$target_company.val(), posting_date: this.$posting_date.val(), gst_type: this.$gst_type.val(), remarks: this.$remarks.val(),
            sales_tax_template: this.$sales_tax_template.val() || "",
            purchase_tax_template: this.$purchase_tax_template.val() || "",
            items: this.items.filter(r => r.item_code).map(r => ({
                item_code: r.item_code, item_name: r.item_name,
                box: r.box, pcs: r.pcs, ltr: r.ltr,
                qty: r.qty, uom: "Litre", rate: r.rate, amount: r.amount,
                source_warehouse: r.source_warehouse, target_warehouse: r.target_warehouse,
            })) };
    }

    save(on_success) {
        const errors = this.validate(); if (errors.length) { frappe.msgprint({title:"Validation Error", indicator:"red", message:errors.join("<br>")}); return; }
        const self = this, data = this.get_save_data();
        self.$status_bar.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Saving...</span>');
        frappe.call({ method: "fast_entry_app.api.ict.create_inter_company_transfer", args: { data: data }, freeze: true, freeze_message: __("Creating Inter Company Transfer..."),
            callback: function(r) { if (r.message && r.message.name) { self.last_saved_name = r.message.name; frappe.show_alert({ message: __("Transfer {0} saved", [r.message.name]), indicator: "green" }); self.$status_bar.html('<span class="fe-status-ok"><i class="fa fa-check"></i> Saved: <a href="/app/inter-company-transfer/' + r.message.name + '" target="_blank">' + r.message.name + '</a></span>'); if (on_success) on_success(r.message.name); else self.show_submit_dialog(r.message.name); } },
            error: function() { self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Save failed</span>'); } });
    }

    save_and_new() {
        this.save(() => { this.clear_form(); });
    }

    show_submit_dialog(name) {
        const self = this;
        frappe.confirm(__("Submit {0} to create SO→PO→DN→PR→SI→PI chain?", [name]),
            function() { self.submit_ict(name); },
            function() { window.open("/app/inter-company-transfer/" + name, "_blank"); });
    }

    submit_ict(name) {
        const self = this;
        self.$status_bar.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Creating documents...</span>');
        frappe.call({ method: "fast_entry_app.api.ict.submit_inter_company_transfer", args: { name: name }, freeze: true, freeze_message: __("Creating SO→PO→DN→PR→SI→PI..."),
            callback: function(r) { if (r.message && r.message.status) { self.last_saved_name = name; frappe.show_alert({ message: __("Documents created for {0}", [name]), indicator: "green" }); self.$status_bar.html('<span class="fe-status-ok"><i class="fa fa-check"></i> Done: <a href="/app/inter-company-transfer/' + name + '" target="_blank">' + name + '</a></span>'); self.load_ict_sections(name); } },
            error: function() { self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Submit failed</span>'); } });
    }

    load_ict_sections(name) {
        const self = this;
        this.$root.find("#fe-ict-section").show();
        frappe.call({ method: "fast_entry_app.api.ict.get_progress_status", args: { name: name }, callback: function(r) { if (r.message) self.render_progress(r.message); } });
        frappe.call({ method: "fast_entry_app.api.ict.get_generated_documents", args: { name: name }, callback: function(r) { if (r.message) self.render_documents(r.message, name); } });
        frappe.call({ method: "fast_entry_app.api.ict.get_stock_breakdown", args: { name: name }, callback: function(r) { if (r.message) self.render_stock(r.message); } });
        frappe.call({ method: "fast_entry_app.api.ict.get_ict_details", args: { name: name }, callback: function(r) { if (r.message) self.render_payment_section(r.message, name); } });
    }

    render_progress(steps) {
        const active = steps.filter(s => s.status === "Submitted").length, pct = Math.round((active / steps.length) * 100);
        let h = `<div class="fe-card"><div class="fe-card-header"><i class="fa fa-chain"></i> Document Chain Progress</div>`;
        h += `<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;"><div style="flex:1;height:6px;background:#e5e7eb;border-radius:3px;overflow:hidden;"><div style="height:100%;width:${pct}%;background:linear-gradient(90deg,#3b82f6,#10b981);border-radius:3px;transition:width 0.5s;"></div></div><span style="font-size:11px;font-weight:700;color:${pct===100?'#059669':'#6b7280'};">${pct}%</span></div>`;
        h += `<div style="display:flex;gap:0;">`;
        steps.forEach((s, i) => {
            const done = s.status === "Submitted";
            h += `<div style="flex:1;text-align:center;position:relative;"><div style="width:36px;height:36px;border-radius:50%;margin:0 auto;display:flex;align-items:center;justify-content:center;${done ? 'background:'+s.color+'15;border:2px solid '+s.color+';' : 'background:#f3f4f6;border:2px solid #e5e7eb;'}"><i class="${done ? s.icon : 'fa fa-circle-o'}" style="font-size:12px;color:${done ? s.color : '#9ca3af'};"></i></div><div style="margin-top:4px;font-size:9px;font-weight:700;color:${done ? s.color : '#9ca3af'};">${s.short}</div>`;
            if (s.name) { h += `<div style="margin-top:1px;font-size:8px;max-width:70px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;margin:0 auto;"><a href="/app/${s.doctype.toLowerCase().replace(/ /g,'-')}/${s.name}" target="_blank" style="color:${s.color};text-decoration:none;">${s.name}</a></div>`; }
            else { h += `<div style="margin-top:2px;font-size:8px;color:#d1d5db;">Pending</div>`; }
            h += `</div>`;
            if (i < steps.length - 1) h += `<div style="position:absolute;right:-8px;top:16px;z-index:1;"><div style="width:16px;height:2px;background:${done?'#3b82f6':'#e5e7eb'};"></div></div>`;
        });
        h += `</div></div>`;
        this.$root.find("#fe-progress-section").html(h);
    }

    render_documents(docs, ict_name) {
        if (!docs || !docs.length) return;
        let h = `<div class="fe-card"><div class="fe-card-header"><i class="fa fa-files-o"></i> Generated Documents</div>`;
        h += `<div class="fe-docs-grid">`;
        docs.forEach(d => {
            const done = d.status === "Submitted";
            const border_color = done ? d.color : '#e5e7eb';
            const bg = done ? d.color + '08' : '#f9fafb';
            h += `<div class="fe-doc-card" style="border-left:3px solid ${border_color};background:${bg};">`;
            h += `<div class="fe-doc-header"><span class="fe-doc-badge" style="background:${d.color}20;color:${d.color};">${d.short}</span>`;
            h += `<span class="fe-doc-status ${done ? 'fe-status-submitted' : 'fe-status-draft'}">${d.status}</span></div>`;
            h += `<div class="fe-doc-type">${d.doctype}</div>`;
            if (d.name) {
                const link = `/app/${d.doctype.toLowerCase().replace(/ /g, '-')}/${d.name}`;
                h += `<div class="fe-doc-name"><a href="${link}" target="_blank">${d.name}</a></div>`;
                if (d.net_total) h += `<div class="fe-doc-detail">Base: Rs. ${this.fmt(d.net_total)}</div>`;
                if (d.tax_amount) h += `<div class="fe-doc-detail" style="color:#7c3aed;">Tax (${d.tax_rate}%): Rs. ${this.fmt(d.tax_amount)}</div>`;
                h += `<div class="fe-doc-amount">Grand Total: Rs. ${this.fmt(d.grand_total)}</div>`;
                if (d.fe_box || d.fe_pcs || d.fe_total_ltr) {
                    h += `<div class="fe-doc-detail" style="color:#059669;font-weight:600;">Box: ${d.fe_box||0} | PCS: ${d.fe_pcs||0} | Ltr: ${this.fmt(d.fe_total_ltr||0)}</div>`;
                }
                if (d.outstanding && d.outstanding > 0) h += `<div class="fe-doc-detail" style="color:#ef4444;">Outstanding: Rs. ${this.fmt(d.outstanding)}</div>`;
                h += `<div class="fe-doc-company">${d.company || ''} | ${d.posting_date || ''}</div>`;
            } else {
                h += `<div class="fe-doc-name" style="color:#d1d5db;">Not created</div>`;
            }
            h += `</div>`;
        });
        h += `</div></div>`;
        this.$root.find("#fe-docs-section").html(h);
    }

    render_stock(data) {
        if (!data || !Object.keys(data).length) return;
        const allWh = new Set(), byItem = {};
        Object.keys(data).forEach(ic => { byItem[ic] = {}; (data[ic] || []).forEach(row => { allWh.add(row.warehouse); byItem[ic][row.warehouse] = row; }); });
        const whList = [...allWh];
        let h = `<div class="fe-card"><div class="fe-card-header"><i class="fa fa-cubes"></i> Stock Across Warehouses</div>`;
        h += `<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:11px;"><thead><tr style="background:#f9fafb;"><th style="padding:8px 10px;text-align:left;font-weight:700;color:#6b7280;font-size:10px;">Item</th>`;
        whList.forEach(w => { h += `<th style="padding:8px 6px;text-align:right;font-weight:700;color:#6b7280;font-size:10px;min-width:70px;">${w.split(' - ')[0]}</th>`; });
        h += `<th style="padding:8px 10px;text-align:right;font-weight:700;color:#3b82f6;font-size:10px;">Total</th></tr></thead><tbody>`;
        Object.keys(data).forEach(ic => {
            const rd = byItem[ic] || {}; let tq = 0, tv = 0;
            h += `<tr style="border-bottom:1px solid #f3f4f6;"><td style="padding:8px 10px;font-weight:600;color:#111827;">${ic}</td>`;
            whList.forEach(w => { const c = rd[w], q = c ? c.qty : 0, v = c ? c.val : 0; tq += q; tv += v;
                h += `<td style="padding:6px;text-align:right;"><div style="font-weight:700;color:${q>0?'#059669':q<0?'#dc2626':'#9ca3af'};">${q||'-'}</div><div style="font-size:9px;color:#9ca3af;">Rs.${(v||0).toFixed(0)}</div></td>`; });
            h += `<td style="padding:8px 10px;text-align:right;font-weight:800;color:#3b82f6;"><div>${tq}</div><div style="font-size:9px;">Rs.${tv.toFixed(0)}</div></td></tr>`;
        });
        h += `</tbody></table></div></div>`;
        this.$root.find("#fe-stock-section").html(h);
    }

    render_payment_section(details, ict_name) {
        const self = this;
        if (!details) return;
        const si_outstanding = this.flt(details.si_outstanding || 0);
        const pi_outstanding = this.flt(details.pi_outstanding || 0);
        const has_open = si_outstanding > 0 || pi_outstanding > 0;

        let h = `<div class="fe-card"><div class="fe-card-header"><i class="fa fa-credit-card"></i> Payment Entry (Separate Step)</div>`;
        h += `<div class="fe-payment-grid">`;

        if (details.sales_invoice) {
            h += `<div class="fe-payment-card fe-payment-sell">`;
            h += `<div class="fe-payment-label">SELLING (Source Company)</div>`;
            h += `<div class="fe-payment-doc"><a href="/app/sales-invoice/${details.sales_invoice}" target="_blank">${details.sales_invoice}</a></div>`;
            h += `<div class="fe-payment-meta">Rs. ${this.fmt(details.si_grand_total)} | Outstanding: Rs. ${this.fmt(si_outstanding)}</div>`;
            if (si_outstanding <= 0) h += `<div class="fe-payment-paid"><i class="fa fa-check-circle"></i> Fully Paid</div>`;
            h += `</div>`;
        }

        if (details.purchase_invoice) {
            h += `<div class="fe-payment-card fe-payment-buy">`;
            h += `<div class="fe-payment-label">BUYING (Target Company)</div>`;
            h += `<div class="fe-payment-doc"><a href="/app/purchase-invoice/${details.purchase_invoice}" target="_blank">${details.purchase_invoice}</a></div>`;
            h += `<div class="fe-payment-meta">Rs. ${this.fmt(details.pi_grand_total)} | Outstanding: Rs. ${this.fmt(pi_outstanding)}</div>`;
            if (pi_outstanding <= 0) h += `<div class="fe-payment-paid"><i class="fa fa-check-circle"></i> Fully Paid</div>`;
            h += `</div>`;
        }

        if (has_open) {
            h += `<div class="fe-payment-actions" style="padding:10px 12px;display:flex;align-items:center;gap:10px;">`;
            h += `<button class="fe-btn fe-btn-primary fe-btn-pay-bulk" style="padding:8px 14px;"><i class="fa fa-money"></i> Create Payment Entries</button>`;
            h += `<span style="font-size:10px;color:#6b7280;">Creates Receive (SI) + Pay (PI) together</span>`;
            h += `</div>`;
        }

        h += `</div></div>`;
        this.$root.find("#fe-payment-section").html(h);

        this.$root.find(".fe-btn-pay-bulk").on("click", function() {
            const $btn = $(this).prop("disabled", true);
            $btn.html('<i class="fa fa-spinner fa-spin"></i> Creating...');
            frappe.confirm(__("Create Payment Entries for {0}?", [ict_name]),
                function() {
                    frappe.call({ method: "fast_entry_app.api.ict.create_payment_entries_for_ict",
                        args: { ict_name: ict_name },
                        callback: function(r) {
                            $btn.prop("disabled", false).html('<i class="fa fa-money"></i> Create Payment Entries');
                            if (r.message && r.message.created && r.message.created.length) {
                                frappe.show_alert({ message: __("Payment Entries created: {0}", [r.message.created.join(", ")]), indicator: "green" });
                                self.load_ict_sections(ict_name);
                            } else {
                                frappe.show_alert({ message: __("No payment entries created (already settled)"), indicator: "orange" });
                            }
                        },
                        error: function() { $btn.prop("disabled", false).html('<i class="fa fa-money"></i> Create Payment Entries'); }
                    });
                },
                function() { $btn.prop("disabled", false).html('<i class="fa fa-money"></i> Create Payment Entries'); });
        });
    }

    clear_form() { this.items = []; this.$grid_body.empty(); this.$posting_date.val(frappe.datetime.get_today()); this.$remarks.val(""); this.add_empty_row(); this.update_totals(); this.$status_bar.html(""); this.$root.find("#fe-source-company").focus(); this.$root.find("#fe-ict-section").hide(); }
};
