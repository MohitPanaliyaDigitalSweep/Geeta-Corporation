frappe.provide("fast_entry_app");

frappe.pages["fast-ledger-pnl"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Fast Ledger & P&L"), single_column: true });
    fast_entry_app.ledger_pnl_page = new fast_entry_app.LedgerPNL(wrapper);
};

fast_entry_app.LedgerPNL = class LedgerPNL {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.build();
    }

    flt(v) { return parseFloat(v) || 0; }
    fmt(v) { return (this.flt(v)).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

    build() {
        this.$root = $(this.wrapper.page.main);
        this.$root.html(this.get_html());
        this.bind_elements();
        this.load_companies();
    }

    get_html() {
        const today = frappe.datetime.get_today();
        const first = today.slice(0, 8) + "01";
        return `<div class="fast-entry-container fsr-container">
            <div class="fe-header-section">
                <div class="fe-header-row">
                    <div class="fe-field"><label>Company <span class="reqd">*</span></label><select class="fe-input" id="flp-company"></select></div>
                    <div class="fe-field"><label>From Date</label><input type="date" class="fe-input" id="flp-from" value="${first}" /></div>
                    <div class="fe-field"><label>To Date</label><input type="date" class="fe-input" id="flp-to" value="${today}" /></div>
                    <div class="fe-field" style="flex:0 0 130px;align-self:flex-end;"><button class="fe-btn fe-btn-primary" id="flp-load" style="width:100%;justify-content:center;"><i class="fa fa-search"></i> Load</button></div>
                </div>
                <div class="flp-tabs">
                    <button class="flp-tab flp-tab-active" data-tab="ledger"><i class="fa fa-book"></i> Ledger</button>
                    <button class="flp-tab" data-tab="pnl"><i class="fa fa-line-chart"></i> Profit &amp; Loss</button>
                </div>
            </div>

            <div class="flp-panel" id="flp-ledger-panel">
                <div class="fe-card">
                    <div class="fe-card-header"><i class="fa fa-book"></i> General Ledger <span class="fsr-summary-sub" id="flp-ledger-sub"></span></div>
                    <div class="fe-header-row" style="display:flex;gap:12px;margin-bottom:10px;">
                        <div class="fe-field" style="flex:0 0 160px;"><label>Party Type</label><select class="fe-input" id="flp-party-type"><option value="">All</option><option value="Customer">Customer</option><option value="Supplier">Supplier</option></select></div>
                        <div class="fe-field fe-field-wide"><label>Party</label><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-input" id="flp-party" placeholder="Search party..." autocomplete="off" /></div></div>
                        <div class="fe-field fe-field-wide"><label>Account</label><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-input" id="flp-account" placeholder="Search account..." autocomplete="off" /></div></div>
                        <div class="fe-field" style="flex:0 0 80px;align-self:flex-end;"><button class="fe-btn fe-btn-sm fe-btn-primary" id="flp-ledger-refresh" style="width:100%;height:36px;justify-content:center;"><i class="fa fa-refresh"></i> Go</button></div>
                    </div>
                    <div id="flp-ledger-wrap" style="overflow-x:auto;">
                        <table class="fsr-table" id="flp-ledger-table">
                            <thead><tr>
                                <th>Date</th>
                                <th>Voucher Type</th>
                                <th>Voucher No</th>
                                <th>Party</th>
                                <th>Account</th>
                                <th class="fsr-num">Debit (Rs)</th>
                                <th class="fsr-num">Credit (Rs)</th>
                                <th class="fsr-num">Balance (Rs)</th>
                            </tr></thead>
                            <tbody id="flp-ledger-body"></tbody>
                            <tfoot id="flp-ledger-total"></tfoot>
                        </table>
                    </div>
                    <div class="fsr-empty" id="flp-ledger-empty" style="display:none;">No ledger entries found for the selected filters.</div>
                </div>
            </div>

            <div class="flp-panel" id="flp-pnl-panel" style="display:none;">
                <div class="fe-card">
                    <div class="fe-card-header"><i class="fa fa-line-chart"></i> Profit &amp; Loss <span class="fsr-summary-sub" id="flp-pnl-sub"></span></div>
                    <div id="flp-pnl-wrap" style="overflow-x:auto;">
                        <table class="fsr-table" id="flp-pnl-table">
                            <thead id="flp-pnl-thead"></thead>
                            <tbody id="flp-pnl-body"></tbody>
                        </table>
                    </div>
                    <div class="fsr-empty" id="flp-pnl-empty" style="display:none;">No income or expense entries found in this period.</div>
                </div>
            </div>
        </div>`;
    }

    bind_elements() {
        const self = this;
        this.$company = this.$root.find("#flp-company");
        this.$from = this.$root.find("#flp-from");
        this.$to = this.$root.find("#flp-to");
        this.$party_type = this.$root.find("#flp-party-type");
        this.$party = this.$root.find("#flp-party");
        this.$account = this.$root.find("#flp-account");
        this.$ledger_body = this.$root.find("#flp-ledger-body");
        this.$ledger_total = this.$root.find("#flp-ledger-total");
        this.$ledger_empty = this.$root.find("#flp-ledger-empty");
        this.$pnl_thead = this.$root.find("#flp-pnl-thead");
        this.$pnl_body = this.$root.find("#flp-pnl-body");
        this.$pnl_empty = this.$root.find("#flp-pnl-empty");

        this.$company.on("change", () => {
            localStorage.setItem("flp_company", this.$company.val());
            this.load_ledger();
            this.load_pnl();
        });
        this.$root.find("#flp-load").on("click", () => { this.load_ledger(); this.load_pnl(); });
        this.$root.find("#flp-ledger-refresh").on("click", () => this.load_ledger());
        this.$root.find(".flp-tab").on("click", function() {
            const tab = $(this).data("tab");
            self.$root.find(".flp-tab").removeClass("flp-tab-active");
            $(this).addClass("flp-tab-active");
            self.$root.find(".flp-panel").hide();
            self.$root.find("#flp-" + tab + "-panel").show();
            if (tab === "ledger") self.load_ledger();
            else self.load_pnl();
        });

        this.bind_autocomplete(this.$party, (val, cb) => {
            frappe.call({
                method: "fast_entry_app.api.ledger_pnl.search_all_parties",
                args: { search: val, limit: 12 },
                callback: function(r) { cb(r.message || []); }
            });
        }, (item) => {
            this.$party.val(item.full_name || item.name);
        }, "full_name", "name");

        this.bind_autocomplete(this.$account, (val, cb) => {
            frappe.call({
                method: "fast_entry_app.api.ledger_pnl.search_accounts",
                args: { company: this.$company.val(), search: val, limit: 12 },
                callback: function(r) { cb(r.message || []); }
            });
        }, (item) => {
            this.$account.val(item.account_name || item.name);
        }, "account_name", "name");
    }

    bind_autocomplete($input, search_fn, select_fn, primary_field, name_field) {
        const self = this;
        let timer = null;
        $input.on("input", function() {
            clearTimeout(timer);
            const val = $(this).val();
            if (val.length < 1) { self.hide_dropdown(); return; }
            timer = setTimeout(() => {
                search_fn(val, function(items) {
                    if (!items || !items.length) { self.hide_dropdown(); return; }
                    self._ac_items = items;
                    let html = "";
                    items.forEach(function(item) {
                        const primary = item[primary_field] || item.name;
                        const secondary = item[name_field] || item.name;
                        const tag = item.party_type ? `<span class="fe-dd-secondary" style="margin-left:12px;">${item.party_type}</span>` : "";
                        const display = primary !== secondary
                            ? `<span class="fe-dd-primary">${primary}</span><span class="fe-dd-secondary">${secondary}</span>${tag}`
                            : `<span class="fe-dd-primary">${primary}</span>${tag}`;
                        html += `<div class="fe-dropdown-item" data-code="${item.name}">${display}</div>`;
                    });
                    self.$dd = self.show_dropdown($input, html, function($el) {
                        const picked = (self._ac_items || []).find(i => i.name === $el.data("code")) || {};
                        select_fn(picked);
                    });
                });
            }, 200);
        });
        $input.on("keydown", function(e) {
            const $items = self.$dd ? self.$dd.find(".fe-dropdown-item") : $();
            const $active = $items.filter(".active");
            if (e.key === "ArrowDown") { e.preventDefault(); if (!$active.length) $items.first().addClass("active"); else $active.removeClass("active").next().addClass("active"); }
            else if (e.key === "ArrowUp") { e.preventDefault(); if (!$active.length) $items.last().addClass("active"); else $active.removeClass("active").prev().addClass("active"); }
            else if (e.key === "Enter") { e.preventDefault(); if ($active.length) $active.trigger("mousedown"); }
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
        frappe.call({ method: "frappe.client.get_list", args: { doctype: "Company", filters: {}, fields: ["name"], limit_page_length: 100 },
            callback: function(r) {
                const companies = r.message || [];
                self.$company.empty().append('<option value="">Select Company</option>');
                companies.forEach(c => self.$company.append(`<option value="${c.name}">${c.name}</option>`));
                const ls = localStorage.getItem("flp_company");
                if (ls && companies.find(c => c.name === ls)) { self.$company.val(ls); self.load_ledger(); self.load_pnl(); }
            }
        });
    }

    load_ledger() {
        const company = this.$company.val();
        if (!company) return;
        const self = this;
        this.$ledger_body.html(`<tr><td colspan="8" style="text-align:center;padding:20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin"></i> Loading ledger...</td></tr>`);
        this.$ledger_total.html("");
        this.$ledger_empty.hide();
        frappe.call({
            method: "fast_entry_app.api.ledger_pnl.get_ledger",
            args: {
                company: company,
                from_date: this.$from.val() || "",
                to_date: this.$to.val() || "",
                party_type: this.$party_type.val() || "",
                party: this.$party.val() || "",
                account: this.$account.val() || "",
            },
            callback: function(r) { self.render_ledger(r.message || {}); },
            error: function() { self.$ledger_body.html(`<tr><td colspan="8" style="text-align:center;padding:20px;color:#ef4444;">Failed to load ledger.</td></tr>`); }
        });
    }

    render_ledger(data) {
        const rows = data.rows || [];
        this.$ledger_body.empty();
        this.$ledger_total.html("");
        if (!rows.length) { this.$ledger_empty.show(); this.$root.find("#flp-ledger-sub").text(""); return; }
        this.$ledger_empty.hide();
        const self = this;
        let total_dr = 0, total_cr = 0;

        rows.forEach(function(r) {
            const account = (r.account || "").replace(/^'+|'+$/g, "");
            const is_opening = r.voucher_type === "Opening" || account === "Opening";
            const is_sep = !r.voucher_type && !r.account && r.balance === 0;
            if (is_sep) { return; }
            const debit = self.flt(r.debit), credit = self.flt(r.credit);
            total_dr += debit; total_cr += credit;
            const bal = self.flt(r.balance);
            const bal_color = bal > 0 ? "#059669" : bal < 0 ? "#dc2626" : "#9ca3af";
            const vname = r.voucher_no || "";
            const vtype = r.voucher_type || "";
            const link = vtype && vname ? `<a href="/app/${vtype.toLowerCase().replace(/ /g, "-")}/${vname}" target="_blank">${vname}</a>` : (vname || "");
            const tr = document.createElement("tr");
            tr.className = is_opening ? "flp-opening" : "";
            tr.innerHTML = `
                <td class="fsr-date">${r.posting_date || (is_opening ? "Opening" : "")}</td>
                <td>${is_opening ? "Opening" : vtype}</td>
                <td>${is_opening ? "" : link}</td>
                <td>${r.party || ""}</td>
                <td>${account}</td>
                <td class="fsr-num">${debit ? self.fmt(debit) : ""}</td>
                <td class="fsr-num">${credit ? self.fmt(credit) : ""}</td>
                <td class="fsr-num" style="font-weight:700;color:${bal_color};">${self.fmt(bal)}</td>`;
            self.$ledger_body[0].appendChild(tr);
        });

        this.$root.find("#flp-ledger-sub").text(`${rows.length - 1} entries | ${this.$party.val() ? "Party: " + this.$party.val() : "All parties"}`);
        this.$ledger_total.html(`<tr style="background:#f9fafb;border-top:2px solid #e5e7eb;">
            <td colspan="5" style="padding:8px 10px;font-weight:700;color:#374151;">Totals</td>
            <td class="fsr-num" style="padding:8px 10px;font-weight:700;">${self.fmt(total_dr)}</td>
            <td class="fsr-num" style="padding:8px 10px;font-weight:700;">${self.fmt(total_cr)}</td>
            <td class="fsr-num" style="padding:8px 10px;font-weight:700;">${self.fmt(total_dr - total_cr)}</td>
        </tr>`);
    }

    load_pnl() {
        const company = this.$company.val();
        if (!company) return;
        const self = this;
        this.$pnl_body.html(`<tr><td colspan="20" style="text-align:center;padding:20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin"></i> Loading P&amp;L...</td></tr>`);
        this.$pnl_empty.hide();
        frappe.call({
            method: "fast_entry_app.api.ledger_pnl.get_pnl",
            args: { company: company, from_date: this.$from.val() || "", to_date: this.$to.val() || "" },
            callback: function(r) { self.render_pnl(r.message || {}); },
            error: function() { self.$pnl_body.html(`<tr><td colspan="20" style="text-align:center;padding:20px;color:#ef4444;">Failed to load P&amp;L.</td></tr>`); }
        });
    }

    render_pnl(data) {
        const periods = data.periods || [];
        const labels = data.period_labels || {};
        const rows = data.rows || [];
        this.$pnl_body.empty();

        let thead = `<tr><th>Account</th>`;
        periods.forEach(p => thead += `<th class="fsr-num">${labels[p] || p}</th>`);
        thead += `<th class="fsr-num">Total</th></tr>`;
        this.$pnl_thead.html(thead);

        if (!rows.length) { this.$pnl_empty.show(); this.$root.find("#flp-pnl-sub").text(""); return; }
        this.$pnl_empty.hide();
        const self = this;
        this.$root.find("#flp-pnl-sub").text(`${labels[periods[0]] || periods[0]} to ${labels[periods[periods.length - 1]] || periods[periods.length - 1]} | ${this.$company.val()}`);

        let last_type = null;

        rows.forEach(function(r) {
            const amt = self.flt(r.total);
            const is_income = r.root_type === "Income";
            const tr = document.createElement("tr");

            if (r.root_type !== last_type) {
                const hdr_tr = document.createElement("tr");
                hdr_tr.className = "flp-section-header";
                hdr_tr.innerHTML = `<td colspan="${periods.length + 2}" style="font-weight:800;font-size:12px;text-transform:uppercase;color:#374151;padding:10px 8px 4px;border-bottom:2px solid #1a1a2e;">${is_income ? "Income" : "Expenses"}</td>`;
                self.$pnl_body[0].appendChild(hdr_tr);
                last_type = r.root_type;
            }

            let cells = `<td style="padding-left:${12 + r.indent * 18}px;font-weight:600;">${r.name}</td>`;
            periods.forEach(p => {
                const v = self.flt(r.periods[p]);
                cells += `<td class="fsr-num" style="${v < 0 ? "color:#dc2626;" : ""}">${v ? self.fmt(v) : ""}</td>`;
            });
            cells += `<td class="fsr-num" style="font-weight:700;color:${amt < 0 ? "#dc2626" : is_income ? "#059669" : "#1a1a2e"};">${self.fmt(amt)}</td>`;
            tr.innerHTML = cells;
            self.$pnl_body[0].appendChild(tr);
        });

        // Income total
        const inc_tr = document.createElement("tr");
        inc_tr.className = "flp-total-row";
        let inc_cells = `<td style="padding-left:8px;font-weight:800;">Total Income</td>`;
        periods.forEach(p => {
            let pv = 0;
            rows.forEach(r => { if (r.root_type === "Income") pv += self.flt(r.periods[p]); });
            inc_cells += `<td class="fsr-num" style="font-weight:700;color:${pv < 0 ? "#dc2626" : "#059669"};">${pv ? self.fmt(pv) : ""}</td>`;
        });
        inc_cells += `<td class="fsr-num" style="font-weight:800;color:#059669;">${self.fmt(data.income_total)}</td>`;
        inc_tr.innerHTML = inc_cells;
        self.$pnl_body[0].appendChild(inc_tr);

        // Expense total
        const exp_tr = document.createElement("tr");
        exp_tr.className = "flp-total-row";
        let exp_cells = `<td style="padding-left:8px;font-weight:800;">Total Expenses</td>`;
        periods.forEach(p => {
            let pv = 0;
            rows.forEach(r => { if (r.root_type === "Expense") pv += self.flt(r.periods[p]); });
            exp_cells += `<td class="fsr-num" style="font-weight:700;color:${pv < 0 ? "#dc2626" : "#1a1a2e"};">${pv ? self.fmt(pv) : ""}</td>`;
        });
        exp_cells += `<td class="fsr-num" style="font-weight:800;color:#1a1a2e;">${self.fmt(data.expense_total)}</td>`;
        exp_tr.innerHTML = exp_cells;
        self.$pnl_body[0].appendChild(exp_tr);

        // Net Profit
        const net = self.flt(data.net_profit);
        const net_tr = document.createElement("tr");
        net_tr.className = "flp-net-row";
        let net_cells = `<td style="padding-left:8px;font-weight:800;">Net Profit (Income - Expense)</td>`;
        periods.forEach(p => {
            let period_income = 0, period_expense = 0;
            rows.forEach(r => {
                const v = self.flt(r.periods[p]);
                if (r.root_type === "Income") period_income += v;
                else period_expense += v;
            });
            const period_net = period_income - period_expense;
            net_cells += `<td class="fsr-num" style="font-weight:700;color:${period_net >= 0 ? "#059669" : "#dc2626"};">${self.fmt(period_net)}</td>`;
        });
        net_cells += `<td class="fsr-num" style="font-weight:800;color:${net >= 0 ? "#059669" : "#dc2626"};">${self.fmt(net)}</td>`;
        net_tr.innerHTML = net_cells;
        this.$pnl_body[0].appendChild(net_tr);
    }
};