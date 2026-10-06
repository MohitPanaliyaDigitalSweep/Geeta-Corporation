frappe.provide("fast_entry_app");

frappe.pages["fast-stock-report"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Fast Stock Report"), single_column: true });
    fast_entry_app.stock_report_page = new fast_entry_app.StockReport(wrapper);
};

fast_entry_app.StockReport = class StockReport {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.rows = [];
        this.breakdown = {};
        this.build();
    }

    flt(v) { return parseFloat(v) || 0; }
    fmt(v) { return (this.flt(v)).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
    fmt_int(v) { return (this.flt(v)).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

    build() {
        this.$root = $(this.wrapper.page.main);
        this.$root.html(this.get_html());
        this.bind_elements();
        this.load_companies();
    }

    get_html() {
        return `<div class="fast-entry-container fsr-container">
            <div class="fe-header-section">
                <div class="fe-header-row">
                    <div class="fe-field" style="flex:0 0 320px;"><label>Company</label>
                        <select class="fe-input" id="fsr-company"><option value="">Select Company</option></select>
                    </div>
                    <div class="fe-field"><label>Warehouse</label><select class="fe-input" id="fsr-warehouse"><option value="">All Warehouses</option></select></div>
                    <div class="fe-field fe-field-wide"><label>Search Item</label><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-input" id="fsr-item-search" placeholder="Search by item name or code..." autocomplete="off" /></div></div>
                    <div class="fe-field" style="flex:0 0 130px;align-self:flex-end;"><button class="fe-btn fe-btn-primary" id="fsr-load" style="width:100%;justify-content:center;"><i class="fa fa-search"></i> Load Stock</button></div>
                </div>
            </div>

            <div class="fe-card fsr-summary-card">
                <div class="fe-card-header"><i class="fa fa-cubes"></i> Stock Balance <span class="fsr-summary-sub" id="fsr-summary-sub"></span></div>
                <div id="fsr-summary-wrap" style="overflow-x:auto;">
                    <table class="fsr-table" id="fsr-summary-table">
                        <thead><tr>
                            <th class="fsr-col-expand"></th>
                            <th>Item Code</th>
                            <th>Item Name</th>
                            <th id="fsr-wh-head">Warehouse</th>
                            <th class="fsr-num">Nos (Pcs)</th>
                            <th class="fsr-num">Box</th>
                            <th class="fsr-num">LTR</th>
                            <th class="fsr-num">Valuation Rate</th>
                            <th class="fsr-num">Stock Value (Rs)</th>
                        </tr></thead>
                        <tbody id="fsr-summary-body"></tbody>
                    </table>
                </div>
                <div class="fsr-empty" id="fsr-summary-empty" style="display:none;">No stock found for the selected filters.</div>
            </div>

            <div class="fe-card fsr-tx-card" id="fsr-tx-card" style="display:none;">
                <div class="fe-card-header">
                    <span><i class="fa fa-list-alt"></i> Transactions: <b id="fsr-tx-item-name"></b></span>
                    <span class="fsr-tx-actions">
                        <button class="fe-btn fe-btn-sm" id="fsr-tx-back"><i class="fa fa-arrow-left"></i> Back</button>
                    </span>
                </div>
                <div class="fe-header-row" style="display:flex;gap:12px;margin-bottom:10px;">
                    <div class="fe-field" style="flex:0 0 220px;"><label>Warehouse</label><select class="fe-input" id="fsr-tx-warehouse"></select></div>
                    <div class="fe-field" style="flex:0 0 160px;"><label>From Date</label><input type="date" class="fe-input" id="fsr-tx-from" /></div>
                    <div class="fe-field" style="flex:0 0 160px;"><label>To Date</label><input type="date" class="fe-input" id="fsr-tx-to" /></div>
                    <div class="fe-field" style="flex:0 0 100px;align-self:flex-end;"><button class="fe-btn fe-btn-sm fe-btn-primary" id="fsr-tx-refresh" style="width:100%;justify-content:center;"><i class="fa fa-refresh"></i> Refresh</button></div>
                </div>
                <div id="fsr-tx-wrap" style="overflow-x:auto;">
                    <table class="fsr-table" id="fsr-tx-table">
                        <thead><tr>
                            <th id="fsr-tx-co-head" style="display:none;">Company</th>
                            <th>Date</th>
                            <th>Voucher Type</th>
                            <th>Voucher No</th>
                            <th>Warehouse</th>
                            <th class="fsr-num">In</th>
                            <th class="fsr-num">Out</th>
                            <th class="fsr-num">Balance</th>
                            <th class="fsr-num">Rate</th>
                            <th class="fsr-num">Value Diff (Rs)</th>
                        </tr></thead>
                        <tbody id="fsr-tx-body"></tbody>
                        <tfoot id="fsr-tx-total"></tfoot>
                    </table>
                </div>
                <div class="fsr-empty" id="fsr-tx-empty" style="display:none;">No transactions found for the selected filters.</div>
            </div>
        </div>`;
    }

    bind_elements() {
        this.$company = this.$root.find("#fsr-company");
        this.$warehouse = this.$root.find("#fsr-warehouse");
        this.$item_search = this.$root.find("#fsr-item-search");
        this.$summary_body = this.$root.find("#fsr-summary-body");
        this.$summary_empty = this.$root.find("#fsr-summary-empty");
        this.$tx_card = this.$root.find("#fsr-tx-card");
        this.$tx_body = this.$root.find("#fsr-tx-body");
        this.$tx_total = this.$root.find("#fsr-tx-total");
        this.$tx_warehouse = this.$root.find("#fsr-tx-warehouse");
        this.$tx_from = this.$root.find("#fsr-tx-from");
        this.$tx_to = this.$root.find("#fsr-tx-to");

        this.$company.on("change", () => {
            localStorage.setItem("fsr_company", this.$company.val());
            this.hide_transactions();
            this.load_warehouses();
            this.load_stock();
        });
        this.$warehouse.on("change", () => {
            localStorage.setItem("fsr_warehouse", this.$warehouse.val());
            this.hide_transactions();
            this.load_stock();
        });
        this.$root.find("#fsr-load").on("click", () => {
            this.hide_transactions();
            this.load_stock();
        });
        this.$root.find("#fsr-tx-refresh").on("click", () => this.load_transactions());
        this.$root.find("#fsr-tx-back").on("click", () => this.hide_transactions());

        this.bind_item_search();
        this.$tx_from.val(frappe.datetime.add_days(frappe.datetime.get_today(), -30));
        this.$tx_to.val(frappe.datetime.get_today());
    }

    get_selected_companies() {
        return this.$company.val() || "";
    }

    bind_item_search() {
        const self = this;
        const $input = this.$item_search;
        let timer = null;
        $input.on("input", function() {
            clearTimeout(timer);
            const val = $(this).val();
            if (val.length < 1) { self.hide_dropdown(); return; }
            timer = setTimeout(() => {
                frappe.call({
                    method: "fast_entry_app.api.item.search_items",
                    args: { search: val, company: self.get_selected_companies(), limit: 12 },
                    callback: function(r) {
                        let html = "";
                        (r.message || []).forEach(function(item) {
                            html += `<div class="fe-dropdown-item" data-code="${item.item_code}"><span class="fe-dd-primary">${item.item_name || item.item_code}</span><span class="fe-dd-secondary">${item.item_code}</span></div>`;
                        });
                        if (html) {
                            self.$dd = self.show_dropdown($input, html, function($el) {
                                self.load_stock($el.data("code"));
                            });
                        } else {
                            self.hide_dropdown();
                        }
                    }
                });
            }, 200);
        });
        $input.on("keydown", function(e) {
            const $items = self.$dd ? self.$dd.find(".fe-dropdown-item") : $();
            const $active = $items.filter(".active");
            if (e.key === "ArrowDown") { e.preventDefault(); if (!$active.length) $items.first().addClass("active"); else $active.removeClass("active").next().addClass("active"); }
            else if (e.key === "ArrowUp") { e.preventDefault(); if (!$active.length) $items.last().addClass("active"); else $active.removeClass("active").prev().addClass("active"); }
            else if (e.key === "Enter") { e.preventDefault(); if ($active.length) $active.trigger("mousedown"); else self.load_stock($input.val()); }
            else if (e.key === "Escape") { self.hide_dropdown(); }
        });
        $input.on("blur", () => setTimeout(() => this.hide_dropdown(), 150));
    }

    show_dropdown($input, html, select_handler) {
        this.hide_dropdown();
        const $dd = $('<div class="fe-global-dropdown"></div>').appendTo("body").html(html).show();
        $dd.on("mousedown", ".fe-dropdown-item", (e) => {
            e.preventDefault();
            select_handler($(e.currentTarget));
            this.hide_dropdown();
        });
        const rect = $input[0].getBoundingClientRect();
        $dd.css({ top: rect.bottom + 1, left: rect.left, width: Math.max(rect.width, 250) });
        return $dd;
    }

    hide_dropdown() { if (this.$dd) { this.$dd.hide().remove(); this.$dd = null; } }

    load_companies() {
        const self = this;
        frappe.call({ method: "frappe.client.get_list", args: { doctype: "Company", filters: {}, fields: ["name", "abbr"], limit_page_length: 100 },
            callback: function(r) {
                const companies = r.message || [];
                self.companies = companies;
                self.company_abbr = {};
                companies.forEach(c => { self.company_abbr[c.name] = c.abbr || ""; });

                // "All Companies" is the default view: every company's stock in
                // one place, each row badged with its owning company.
                self.$company.append('<option value="__all__">All Companies</option>');
                companies.forEach(c => self.$company.append(`<option value="${c.name}">${c.name}</option>`));

                const ls = localStorage.getItem("fsr_company");
                // remember the last company, but fall back to All Companies
                if (ls === "__all__" || !ls || !companies.find(c => c.name === ls)) {
                    self.$company.val("__all__");
                } else {
                    self.$company.val(ls);
                }
                self.load_warehouses();
                self.load_stock();
            }
        });
    }

    is_all_companies() { return this.$company.val() === "__all__"; }

    esc(v) { return frappe.utils.escape_html(v == null ? "" : String(v)); }

    // Box and LTR are computed from the piece balance, so hovering must show
    // the pack being applied rather than letting the number look like storage.
    factor_tip(r) {
        const f = this.flt(r.box_factor);
        if (!f) return 'title="No Box conversion for this item - boxes not applicable"';
        return `title="${this.fmt_int(f)} Nos per Box"`;
    }

    litre_tip(r) {
        const f = this.flt(r.litre_per_piece);
        if (!f) return 'title="No Litre conversion for this item"';
        return `title="${this.fmt(f)} Litre per piece"`;
    }

    company_badge(company) {
        if (!company) return "";
        const abbr = (this.company_abbr || {})[company] || company;
        const cls = "fsr-co-" + String(abbr).toLowerCase().replace(/[^a-z0-9]/g, "");
        return `<span class="fsr-co-badge ${cls}" title="${this.esc(company)}">${this.esc(abbr)}</span>`;
    }

    load_warehouses() {
        const self = this;
        const company = this.get_selected_companies();
        this.$warehouse.empty().append('<option value="">All Warehouses</option>');
        if (!company) return;
        frappe.call({ method: "fast_entry_app.api.stock_report.get_warehouses", args: { company: company },
            callback: function(r) {
                (r.message || []).forEach(w => self.$warehouse.append(`<option value="${w.name}">${self.esc(w.label || w.warehouse_name || w.name)}</option>`));
                const ls = localStorage.getItem("fsr_warehouse");
                if (ls && (r.message || []).find(w => w.name === ls)) self.$warehouse.val(ls);
            }
        });
    }

    load_stock(search) {
        const company = this.get_selected_companies();
        if (!company) { frappe.msgprint({ title: "Company Required", indicator: "orange", message: "Select at least one company." }); return; }
        const self = this;
        const search_val = search || this.$item_search.val();
        const warehouse = this.$warehouse.val();
        this.$summary_body.html(`<tr><td colspan="9" style="text-align:center;padding:20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin"></i> Loading stock...</td></tr>`);
        frappe.call({ method: "fast_entry_app.api.stock_report.get_stock_summary", args: { company: company, warehouse: warehouse, search: search_val },
            callback: function(r) {
                const data = r.message || {};
                self.rows = data.rows || [];
                self.breakdown = data.breakdown || {};
                self.all_companies = !!data.all_companies;
                self.render_summary(search_val);
            },
            error: function() {
                self.$summary_body.html(`<tr><td colspan="9" style="text-align:center;padding:20px;color:#ef4444;">Failed to load stock.</td></tr>`);
            }
        });
    }

    render_summary(search_val) {
        const self = this;
        this.$summary_body.empty();
        if (!this.rows.length) {
            this.$summary_empty.show();
            this.$root.find("#fsr-summary-sub").text("");
            return;
        }
        this.$summary_empty.hide();
        const sum = (f) => this.rows.reduce((s, r) => s + this.flt(r[f]), 0);
        const total_nos = sum("qty_nos");
        const total_box = sum("qty_box");
        const total_ltr = sum("qty_ltr");
        const total_value = sum("stock_value");
        const co_count = this.rows.reduce((s, r) => s + ((r.companies || []).length), 0);
        const sub = `${this.rows.length} items | ${this.fmt_int(total_nos)} Nos | ${this.fmt_int(total_box)} Box | ${this.fmt(total_ltr)} LTR | Total Value: Rs. ${this.fmt(total_value)}`;
        this.$root.find("#fsr-summary-sub").text(this.all_companies ? `${sub} | across ${co_count} company/item holdings` : sub);

        const single_wh = this.$warehouse.val() ? true : false;
        // In the All Companies view the Warehouse column leads with a company
        // badge so it is obvious who owns each line.
        const show_badge = !!this.all_companies;
        this.$root.find("#fsr-wh-head").text(show_badge ? "Company / Warehouse" : "Warehouse");

        const wh_cell = function(companies, bd_rows) {
            if (show_badge) {
                const badges = (companies || []).map(c => self.company_badge(c)).join(" ");
                const names = bd_rows.map(b => (b.warehouse || "").split(" - ")[0]).join(", ");
                return `<div class="fsr-wh-stack"><div class="fsr-wh-badges">${badges}</div><div class="fsr-wh-names">${self.esc(names)}</div></div>`;
            }
            const names = bd_rows.map(b => (b.warehouse || "").split(" - ")[0]).join(", ");
            return `<span style="font-size:11px;color:#6b7280;">${self.esc(names)}</span>`;
        };

        this.rows.forEach(function(r) {
            const nos = self.flt(r.qty_nos);
            const nos_color = nos > 0 ? "#059669" : nos < 0 ? "#dc2626" : "#9ca3af";
            const bd_rows = self.breakdown[r.item_code] || [];
            const has_breakdown = bd_rows.length > 1 || (bd_rows.length === 1 && !single_wh);
            const tr = document.createElement("tr");
            tr.className = "fsr-row" + (has_breakdown ? " fsr-expandable" : "");
            tr.dataset.code = r.item_code;
            tr.dataset.name = r.item_name;
            tr.innerHTML = `
                <td class="fsr-col-expand">${has_breakdown ? '<i class="fa fa-chevron-right fsr-chevron"></i>' : ""}</td>
                <td class="fsr-code">${self.esc(r.item_code)}</td>
                <td class="fsr-name">${self.esc(r.item_name || "")}</td>
                <td>${wh_cell(r.companies, bd_rows)}</td>
                <td class="fsr-num" style="font-weight:700;color:${nos_color};">${self.fmt_int(nos)}</td>
                <td class="fsr-num" ${self.factor_tip(r)}>${self.fmt(r.qty_box)}</td>
                <td class="fsr-num" ${self.litre_tip(r)}>${self.fmt(r.qty_ltr)}</td>
                <td class="fsr-num">${nos ? self.fmt(self.flt(r.stock_value) / nos) : '0.00'}</td>
                <td class="fsr-num" style="font-weight:700;">${self.fmt(r.stock_value)}</td>`;
            if (has_breakdown) {
                self.$summary_body[0].appendChild(tr);
                bd_rows.forEach(bd => {
                    const sv = self.flt(bd.stock_value);
                    const nos = self.flt(bd.qty_nos);
                    const vrate = nos ? sv / nos : 0;
                    const short_wh = (bd.warehouse || "").split(" - ")[0] || bd.warehouse;
                    const bd_wh = show_badge
                        ? `<span class="fsr-bd-badge">${self.company_badge(bd.company)}</span><span style="padding-left:4px;">${self.esc(short_wh)}</span>`
                        : self.esc(short_wh);
                    const bd_tr = document.createElement("tr");
                    bd_tr.className = "fsr-breakdown";
                    bd_tr.style.display = "none";
                    bd_tr.innerHTML = `
                        <td></td>
                        <td></td>
                        <td></td>
                        <td style="font-size:11px;color:#6b7280;padding-left:16px;">${bd_wh}</td>
                        <td class="fsr-num">${self.fmt_int(nos)}</td>
                        <td class="fsr-num" ${self.factor_tip(bd)}>${self.fmt(bd.qty_box)}</td>
                        <td class="fsr-num" ${self.litre_tip(bd)}>${self.fmt(bd.qty_ltr)}</td>
                        <td class="fsr-num">${self.fmt(vrate)}</td>
                        <td class="fsr-num">${self.fmt(sv)}</td>`;
                    self.$summary_body[0].appendChild(bd_tr);
                });
            } else {
                self.$summary_body[0].appendChild(tr);
            }
        });

        this.$summary_body.off("click").on("click", "tr.fsr-expandable", function(e) {
            const $chev = $(this).find(".fsr-chevron");
            let $next = $(this).next();
            let $bds = $();
            while ($next.length && !$next.hasClass("fsr-row")) {
                if ($next.hasClass("fsr-breakdown")) $bds = $bds.add($next);
                $next = $next.next();
            }
            if ($bds.length) {
                $bds.toggle();
                $chev.toggleClass("fa-chevron-right fa-chevron-down");
            }
        });
        this.$summary_body.off("dblclick").on("dblclick", "tr.fsr-row", function() {
            self.show_transactions($(this).data("code"), $(this).data("name"));
        });
        this.$root.find(".fsr-row").on("click", function(e) {
            if ($(e.target).closest("td.fsr-col-expand").length) return;
            self.show_transactions($(this).data("code"), $(this).data("name"));
        });
    }

    render_breakdown(item_code) {
        const rows = this.breakdown[item_code] || [];
        if (!rows.length) return "";
        let h = '<table class="fsr-bd-table"><tbody>';
        rows.forEach(r => {
            const sv = this.flt(r.stock_value);
            const nos = this.flt(r.qty_nos);
            const vrate = nos ? sv / nos : 0;
            const short_wh = r.warehouse.split(" - ")[0] || r.warehouse;
            h += `<tr><td></td><td></td><td></td><td>${short_wh}</td><td class="fsr-num">${this.fmt_int(nos)}</td><td class="fsr-num">${this.fmt(r.qty_box)}</td><td class="fsr-num">${this.fmt(r.qty_ltr)}</td><td class="fsr-num">${this.fmt(vrate)}</td><td class="fsr-num">${this.fmt(sv)}</td></tr>`;
        });
        h += '</tbody></table>';
        return h;
    }

    show_transactions(item_code, item_name) {
        const self = this;
        this.current_item = item_code;
        this.$tx_card.show();
        this.$tx_item_name = this.$root.find("#fsr-tx-item-name");
        this.$tx_item_name.text(item_name || item_code);
        this.$tx_card[0].scrollIntoView({ behavior: "smooth", block: "start" });
        this.$tx_warehouse.empty().append('<option value="">All Warehouses</option>');
        const wh = this.$warehouse.val();
        frappe.call({ method: "fast_entry_app.api.stock_report.get_warehouses", args: { company: this.get_selected_companies() },
            callback: function(r) {
                (r.message || []).forEach(w => self.$tx_warehouse.append(`<option value="${w.name}">${self.esc(w.label || w.warehouse_name || w.name)}</option>`));
                if (wh) self.$tx_warehouse.val(wh);
                self.load_transactions();
            }
        });
    }

    load_transactions() {
        const self = this;
        if (!this.current_item) return;
        this.$tx_body.html(`<tr><td colspan="10" style="text-align:center;padding:20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin"></i> Loading transactions...</td></tr>`);
        this.$tx_total.html("");
        this.$root.find("#fsr-tx-empty").hide();
        frappe.call({
            method: "fast_entry_app.api.stock_report.get_item_transactions",
            args: {
                item_code: this.current_item,
                warehouse: this.$tx_warehouse.val() || "",
                from_date: this.$tx_from.val() || "",
                to_date: this.$tx_to.val() || "",
                company: this.get_selected_companies() || "",
            },
            callback: function(r) {
                const rows = r.message || [];
                self.render_transactions(rows);
            },
            error: function() {
                self.$tx_body.html(`<tr><td colspan="10" style="text-align:center;padding:20px;color:#ef4444;">Failed to load transactions.</td></tr>`);
            }
        });
    }

    render_transactions(rows) {
        this.$tx_body.empty();
        this.$tx_total.html("");
        if (!rows.length) {
            this.$root.find("#fsr-tx-empty").show();
            return;
        }
        this.$root.find("#fsr-tx-empty").hide();
        const self = this;
        let total_in = 0, total_out = 0;
        // in the All Companies view a Company column makes the drill-down
        // self-explanatory -- the same item moves in several companies
        this.$root.find("#fsr-tx-co-head").toggle(!!this.all_companies);
        rows.forEach(function(r) {
            const qty = self.flt(r.actual_qty);
            const in_qty = qty > 0 ? qty : "";
            const out_qty = qty < 0 ? -qty : "";
            if (qty > 0) total_in += qty; else total_out += -qty;
            const bal = self.flt(r.qty_after_transaction);
            const bal_color = bal > 0 ? "#059669" : bal < 0 ? "#dc2626" : "#9ca3af";
            const vtype = r.voucher_type || "";
            const vname = r.voucher_no || "";
            const link = vtype && vname ? `<a href="/app/${vtype.toLowerCase().replace(/ /g, "-")}/${vname}" target="_blank">${self.esc(vname)}</a>` : (self.esc(vname));
            const tr = document.createElement("tr");
            const co_cell = self.all_companies
                ? `<td class="fsr-tx-co">${self.company_badge(r.company)}</td>`
                : "";
            tr.innerHTML = `${co_cell}
                <td class="fsr-date">${self.esc(r.posting_date)}</td>
                <td>${self.esc(vtype)}</td>
                <td>${link}</td>
                <td class="fsr-wh">${self.esc(r.warehouse || "")}</td>
                <td class="fsr-num" style="color:#059669;font-weight:600;">${in_qty === "" ? "" : self.fmt_int(in_qty)}</td>
                <td class="fsr-num" style="color:#dc2626;font-weight:600;">${out_qty === "" ? "" : self.fmt_int(out_qty)}</td>
                <td class="fsr-num" style="font-weight:700;color:${bal_color};">${self.fmt_int(bal)}</td>
                <td class="fsr-num">${r.valuation_rate ? self.fmt(r.valuation_rate) : ""}</td>
                <td class="fsr-num">${r.stock_value_difference ? self.fmt(r.stock_value_difference) : "0.00"}</td>`;
            self.$tx_body[0].appendChild(tr);
        });
        this.$tx_total.html(`<tr style="background:#f9fafb;border-top:2px solid #e5e7eb;">
            ${this.all_companies ? "<td></td>" : ""}
            <td colspan="${this.all_companies ? 4 : 4}" style="padding:8px 10px;font-weight:700;color:#374151;">Totals</td>
            <td class="fsr-num" style="padding:8px 10px;font-weight:700;color:#059669;">${this.fmt_int(total_in)}</td>
            <td class="fsr-num" style="padding:8px 10px;font-weight:700;color:#dc2626;">${this.fmt_int(total_out)}</td>
            <td colspan="3"></td></tr>`);
    }

    hide_transactions() {
        this.current_item = null;
        this.$tx_card.hide();
    }
};