frappe.provide("fast_entry_app");

frappe.pages["fast-bulk-payment"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Fast Purchase Payment"), single_column: true });
    fast_entry_app.purchase_payment_page = new fast_entry_app.PurchasePayment(wrapper);
};

fast_entry_app.PurchasePayment = class PurchasePayment {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.pending = [];
        this.deselected = {};
        this.selection = null;
        this.build();
    }

    flt(v) { return parseFloat(v) || 0; }
    fmt(v) { return (this.flt(v)).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
    esc(v) { return frappe.utils.escape_html(v == null ? "" : String(v)); }
    // Effective outstanding after the server's carry-forward plan
    // (book outstanding minus auto-applied advance). "Full" means this.
    eff(inv) { return Math.max(this.flt(inv.outstanding_amount) - this.flt(inv.carry_applied), 0); }

    build() {
        this.$root = $(this.wrapper.page.main);
        this.$root.html(this.get_html());
        this.bind_elements();
        this.load_companies();
        this.load_modes_of_payment();
    }

    get_html() {
        const today = frappe.datetime.get_today();
        return `<div class="fast-entry-container fsr-container">
            <div class="fe-header-section">
                <div class="fe-header-row">
                    <div class="fe-field"><label>Company <span class="reqd">*</span></label><select class="fe-input" id="fpp-company"></select></div>
                    <div class="fe-field fe-field-wide"><label>Supplier <span class="reqd">*</span></label><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-input" id="fpp-supplier" placeholder="Search supplier (IOCL...)" autocomplete="off" /></div></div>
                    <div class="fe-field" style="flex:0 0 120px;align-self:flex-end;"><button class="fe-btn fe-btn-primary" id="fpp-load" style="width:100%;justify-content:center;"><i class="fa fa-search"></i> Load</button></div>
                </div>
                <div class="fe-header-row">
                    <div class="fe-field"><label>Posting Date</label><input type="date" class="fe-input" id="fpp-posting-date" value="${today}" /></div>
                    <div class="fe-field"><label>Mode of Payment</label><select class="fe-input" id="fpp-mode"></select></div>
                    <div class="fe-field"><label>Reference No</label><input type="text" class="fe-input" id="fpp-ref-no" placeholder="Optional" /></div>
                </div>
            </div>

            <div class="fe-card">
                <div class="fe-card-header"><i class="fa fa-file-text-o"></i> Pending Purchase Invoices <span class="fsr-summary-sub" id="fpp-pending-sub"></span></div>
                <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px;">
                    <div class="fe-field"><label>Pay Amount (Rs)</label><input type="number" class="fe-input" id="fpp-amount" min="0" step="0.01" placeholder="Auto-select max PIs" /></div>
                    <div style="flex:0 0 190px;"><button class="fe-btn fe-btn-sm" id="fpp-pay-all" style="width:100%;justify-content:center;height:36px;"><i class="fa fa-check-circle"></i> Select All Full</button></div>
                    <div style="flex:0 0 190px;"><button class="fe-btn fe-btn-sm" id="fpp-deselect-all" style="width:100%;justify-content:center;height:36px;"><i class="fa fa-times-circle"></i> Deselect All</button></div>
                </div>
                <div id="fpp-carry-banner" style="display:none;margin-bottom:10px;padding:8px 10px;background:#fefce8;border:1px solid #fde68a;border-radius:6px;font-size:13px;color:#92400e;"></div>
                <div id="fpp-pending-wrap" style="overflow-x:auto;">
                    <table class="fsr-table" id="fpp-pending-table">
                        <thead><tr>
                            <th style="width:36px;"></th>
                            <th id="fpp-party-head" style="display:none;">Member Party</th>
                            <th>Invoice</th>
                            <th>Date</th>
                            <th>Supplier</th>
                            <th class="fsr-num">Grand Total (Rs)</th>
                            <th class="fsr-num">Outstanding (Rs)</th>
                            <th class="fsr-num">To Pay (Rs)</th>
                            <th class="fsr-num">TDS (Rs)</th>
                            <th class="fsr-num">Advance (Rs)</th>
                            <th>Status</th>
                        </tr></thead>
                        <tbody id="fpp-pending-body"></tbody>
                        <tfoot id="fpp-pending-total"></tfoot>
                    </table>
                </div>
                <div class="fsr-empty" id="fpp-pending-empty" style="display:none;">No pending purchase invoices for this supplier / group.</div>
            </div>

            <div class="fe-card">
                <div class="fe-card-header"><i class="fa fa-money"></i> Payment Details</div>
                <div class="fpp-progress" style="margin-bottom:10px;">
                    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
                        <span id="fpp-progress-label" style="color:#374151;">Paying Rs. 0.00 of Rs. 0.00</span>
                        <span id="fpp-progress-pct" style="font-weight:700;color:#059669;">0%</span>
                    </div>
                    <div style="height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden;">
                        <div id="fpp-progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#059669,#10b981);border-radius:4px;transition:width 0.3s;"></div>
                    </div>
                </div>
                <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;">
                    <div class="fe-field"><label>Selected Invoices</label><span id="fpp-sel-count" style="font-weight:700;">0</span></div>
                    <div class="fe-field"><label>Invoices To Pay (Rs)</label><span class="fpp-selected-total" id="fpp-sel-total" style="font-size:16px;">0.00</span></div>
                    <div class="fe-field" style="flex:0 0 260px;align-self:flex-end;"><button class="fe-btn fe-btn-success" id="fpp-create" style="width:100%;justify-content:center;"><i class="fa fa-check"></i> Create Payment Entry</button></div>
                </div>
                <div id="fpp-net-row" style="display:none;margin-top:10px;padding:8px 10px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:6px;font-size:13px;color:#1e40af;"></div>
                <div class="fsr-empty" id="fpp-result" style="display:none;padding:8px 0;text-align:left;"></div>
            </div>

            <div class="fe-status-bar" id="fpp-status-bar"></div>
        </div>`;
    }

    bind_elements() {
        const self = this;
        this.$company = this.$root.find("#fpp-company");
        this.$supplier = this.$root.find("#fpp-supplier");
        this.$posting_date = this.$root.find("#fpp-posting-date");
        this.$mode = this.$root.find("#fpp-mode");
        this.$ref_no = this.$root.find("#fpp-ref-no");
        this.$amount = this.$root.find("#fpp-amount");
        this.$pending_body = this.$root.find("#fpp-pending-body");
        this.$pending_total = this.$root.find("#fpp-pending-total");
        this.$pending_empty = this.$root.find("#fpp-pending-empty");
        this.$status_bar = this.$root.find("#fpp-status-bar");
        this.$sel_count = this.$root.find("#fpp-sel-count");
        this.$sel_total = this.$root.find("#fpp-sel-total");
        this.$carry_banner = this.$root.find("#fpp-carry-banner");
        this.$net_row = this.$root.find("#fpp-net-row");
        this.$progress_bar = this.$root.find("#fpp-progress-bar");
        this.$progress_pct = this.$root.find("#fpp-progress-pct");
        this.$progress_label = this.$root.find("#fpp-progress-label");
        this.$result = this.$root.find("#fpp-result");

        this.$company.on("change", () => {
            localStorage.setItem("fpp_company", this.$company.val());
            this.deselect_all();
        });
        this.$supplier.on("change", () => this.deselect_all());
        this.$posting_date.on("change", () => this.deselect_all());
        this.$root.find("#fpp-load").on("click", () => this.load_pending());
        this.$root.find("#fpp-pay-all").on("click", () => {
            this.$amount.val(this.total_outstanding || 0);
            this.select_all(true);
        });
        this.$root.find("#fpp-deselect-all").on("click", () => { this.$amount.val(""); this.select_all(false); });
        let timer = null;
        this.$amount.on("input", function() {
            clearTimeout(timer);
            timer = setTimeout(() => {
                self.auto_fill_from_amount();
            }, 120);
        });
        this.$root.find("#fpp-create").on("click", () => this.create_payment());

        this.bind_supplier_autocomplete();
    }

    bind_supplier_autocomplete() {
        const self = this;
        let timer = null;
        this.$supplier.on("input", function() {
            clearTimeout(timer);
            const val = $(this).val();
            if (val.length < 1) { self.selection = null; self.deselect_all(); self.hide_dropdown(); return; }
            if (self.selection && self.selection.name !== val) { self.selection = null; self.deselect_all(); }
            timer = setTimeout(() => {
                frappe.call({
                    method: "fast_entry_app.api.payment.search_payment_parties",
                    args: { party_type: "Supplier", search: val, limit: 12 },
                    callback: function(r) {
                        const result = r.message || {};
                        const items = result.results || result.parties || [];
                        if (!items.length) { self.hide_dropdown(); return; }
                        self._ac_items = items;
                        let html = "";
                        (items || []).forEach(function(item) {
                            if (item.kind === "group") {
                                const members = item.member_count || 0;
                                html += `<div class="fe-dropdown-item fe-dd-group" data-code="GRP:${item.name}" data-name="${item.name}" data-label="${item.label || item.name}">
                                    <span class="fe-dd-primary"><i class="fa fa-users"></i> ${item.label || item.name}</span>
                                    <span class="fe-dd-secondary">Group &middot; ${members} member${members === 1 ? "" : "s"} &middot; pays all together</span></div>`;
                            } else {
                                const sec = item.group ? item.group + " | " + item.name : item.name;
                                html += `<div class="fe-dropdown-item" data-code="${item.name}" data-name="${item.name}" data-party-name="${item.party_name || item.label || item.name}" data-group="${item.group || ""}">
                                    <span class="fe-dd-primary">${item.label || item.name}</span><span class="fe-dd-secondary">${sec}</span></div>`;
                            }
                        });
                        self.show_dropdown(self.$supplier, html, function($el) {
                            const code = $el.data("code") || "";
                            const picked = code.startsWith("GRP:")
                                ? { kind: "group", name: $el.data("name"), label: $el.data("label"), member_count: (self._ac_items.find(i => i.kind === "group" && i.name === $el.data("name")) || {}).member_count || 0 }
                                : (self._ac_items || []).find(i => i.kind !== "group" && i.name === code) || {};
                            picked.kind = picked.kind || "party";
                            if (picked.kind === "group") {
                                self.selection = { kind: "group", name: picked.name, party_name: picked.label, group: picked.name };
                                self.$supplier.val(picked.name).attr("data-party-name", picked.label);
                            } else {
                                self.selection = { kind: "party", name: picked.name, party_name: picked.party_name || picked.label || picked.name, group: picked.group || "" };
                                self.$supplier.val(picked.name).attr("data-party-name", self.selection.party_name);
                            }
                            self.deselect_all();
                        });
                    },
                });
            }, 200);
        });
        this.$supplier.on("keydown", function(e) {
            const $dd = self.$dd;
            if (!self.$dd) return;
            const $items = self.$dd.find(".fe-dropdown-item");
            const $active = $items.filter(".active");
            if (e.key === "ArrowDown") { e.preventDefault(); if (!$active.length) $items.first().addClass("active"); else { $active.removeClass("active").next().addClass("active"); } }
            else if (e.key === "ArrowUp") { e.preventDefault(); if (!$active.length) $items.last().addClass("active"); else { $active.removeClass("active").prev().addClass("active"); } }
            else if (e.key === "Enter") { e.preventDefault(); if ($active.length) $active.trigger("mousedown"); }
            else if (e.key === "Escape") { self.hide_dropdown(); }
        });
        this.$supplier.on("blur", () => setTimeout(() => this.hide_dropdown(), 150));
    }

    is_group_mode() { return !!(this.selection && this.selection.kind === "group"); }

    show_dropdown($input, html, select_handler) {
        this.hide_dropdown();
        const $dd = $('<div class="fe-global-dropdown"></div>').appendTo("body").html(html).show();
        $dd.on("mousedown", ".fe-dropdown-item", (e) => {
            e.preventDefault();
            select_handler($(e.currentTarget));
            this.hide_dropdown();
        });
        const rect = $input[0].getBoundingClientRect();
        $dd.css({ top: rect.bottom + 1, left: rect.left, width: Math.max(rect.width, 280) });
        this.$dd = $dd;
    }

    hide_dropdown() { if (this.$dd) { this.$dd.hide().remove(); this.$dd = null; } }

    load_companies() {
        const self = this;
        frappe.call({ method: "frappe.client.get_list", args: { doctype: "Company", filters: {}, fields: ["name"], limit_page_length: 100 },
            callback: function(r) {
                const companies = r.message || [];
                self.$company.empty().append('<option value="">Select Company</option>');
                companies.forEach(c => self.$company.append(`<option value="${c.name}">${c.name}</option>`));
                const ls = localStorage.getItem("fpp_company");
                if (ls && companies.find(c => c.name === ls)) self.$company.val(ls);
            }
        });
    }

    load_modes_of_payment() {
        const self = this;
        frappe.call({ method: "frappe.client.get_list", args: { doctype: "Mode of Payment", filters: {}, fields: ["name"], limit_page_length: 100 },
            callback: function(r) {
                const modes = r.message || [];
                self.$mode.empty().append('<option value="">Default</option>');
                modes.forEach(m => self.$mode.append(`<option value="${m.name}">${m.name}</option>`));
            }
        });
    }

    load_pending() {
        const company = this.$company.val();
        const party = this.$supplier.val();
        const self = this;
        if (!company || !party) { frappe.msgprint({ title: "Missing Details", indicator: "orange", message: "Select company and supplier first." }); return; }
        const group_mode = this.is_group_mode();
        this.$pending_body.html(`<tr><td colspan="${group_mode ? 11 : 10}" style="text-align:center;padding:20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin"></i> Loading pending invoices...</td></tr>`);
        this.$pending_total.html("");
        this.$pending_empty.hide();
        this.$result.hide();
        this.$carry_banner.hide();
        this.$root.find("#fpp-party-head").toggle(group_mode);
        frappe.call({
            method: group_mode ? "fast_entry_app.api.payment.get_pending_party_group_invoices" : "fast_entry_app.api.payment.get_pending_invoices",
            args: group_mode ? { company: company, party_type: "Supplier", group: party } : { company: company, party_type: "Supplier", party: party },
            callback: function(r) {
                const data = r.message || {};
                self.pending = (data.invoices || []).map(function(inv, i) {
                    inv._idx = i;
                    inv.pay_amount = 0;
                    inv.tds = 0;
                    inv.advance = 0;
                    inv.carry_applied = self.flt(inv.carry_applied);
                    return inv;
                });
                self.group = data.group || "";
                self.by_party = data.by_party || {};
                self.deselected = {};
                self.total_outstanding = self.flt(data.total_outstanding);
                self.advance_balance = self.flt(data.advance_balance);
                self.carry_applied_total = self.flt(data.carry_applied_total);
                self.render_pending();
            },
            error: function() { self.$pending_body.html(`<tr><td colspan="${group_mode ? 11 : 10}" style="text-align:center;padding:20px;color:#ef4444;">Failed to load pending invoices.</td></tr>`); }
        });
    }

    render_pending() {
        const self = this;
        const group_mode = this.is_group_mode();
        this.$pending_body.empty();
        this.$pending_total.html("");
        this.$amount.val("");
        if (!this.pending.length) { this.$pending_empty.show(); this.$root.find("#fpp-pending-sub").text(""); this.update_selected_total(); return; }
        this.$pending_empty.hide();
        this.pending.forEach(function(inv) {
            const tr = document.createElement("tr");
            tr.dataset.idx = inv._idx;
            const member_cell = group_mode ? `<td class="fpp-member">${inv.party_name || inv.supplier || ""}</td>` : "";
            const carry_note = self.flt(inv.carry_applied) > 0 ? `<div style="font-size:11px;color:#b45309;">&minus; Rs. ${self.fmt(inv.carry_applied)} carry</div>` : "";
            tr.innerHTML = `
                <td><input type="checkbox" class="fe-input fpp-tick" data-idx="${inv._idx}" /></td>
                ${member_cell}
                <td><a href="/app/purchase-invoice/${inv.name}" target="_blank">${inv.name}</a></td>
                <td class="fsr-date">${inv.posting_date}</td>
                <td>${inv.party_name || inv.supplier_name || inv.supplier || ""}${inv.supplier !== self.$supplier.val() ? ' <span style="color:#9ca3af;font-size:11px;">(' + inv.supplier + ')</span>' : ""}</td>
                <td class="fsr-num">${self.fmt(inv.grand_total)}</td>
                <td class="fsr-num" style="font-weight:700;color:#dc2626;">${self.fmt(inv.outstanding_amount)}${carry_note}</td>
                <td class="fsr-num"><input type="number" class="fe-input fpp-pay-input" data-idx="${inv._idx}" min="0" step="0.01" value="0" /></td>
                <td class="fsr-num"><input type="number" class="fe-input fpp-tds-input" data-idx="${inv._idx}" min="0" step="0.01" value="0" /></td>
                <td class="fsr-num"><input type="number" class="fe-input fpp-adv-input" data-idx="${inv._idx}" min="0" step="0.01" value="0" /></td>
                <td class="fpp-status-cell"></td>`;
            self.$pending_body[0].appendChild(tr);
        });

        self.subtitle();
        self.render_carry_banner();

        if (group_mode && Object.keys(this.by_party).length) {
            Object.keys(this.by_party).forEach(function(pkey) {
                const entry = self.by_party[pkey];
                const adv_note = self.flt(entry.advance_balance) > 0 ? ` &middot; adv Rs. ${self.fmt(entry.advance_balance)}` : "";
                const $sub = $(`<tr class="fpp-member-sub"><td colspan="2" style="padding:6px 10px;font-weight:600;color:#1d4ed8;">${self.esc(entry.party_name || pkey)}</td><td colspan="2" style="padding:6px 0;color:#6b7280;">${entry.invoices.length} invoice${entry.invoices.length === 1 ? "" : "s"}${adv_note}</td><td></td><td></td><td class="fsr-num" style="padding:6px 0;font-weight:600;color:#374151;">${self.fmt(entry.total)}</td><td></td><td></td><td></td><td></td></tr>`);
                self.$pending_body[0].appendChild($sub[0]);
            });
        }

        this.$pending_total.html(`<tr style="background:#f9fafb;border-top:2px solid #e5e7eb;">
            <td colspan="${group_mode ? 6 : 5}" style="padding:8px 10px;font-weight:700;color:#374151;">Total Outstanding</td>
            <td class="fsr-num" style="padding:8px 10px;font-weight:800;color:#dc2626;">${self.fmt(this.total_outstanding)}</td>
            <td class="fsr-num" id="fpp-total-to-pay" style="padding:8px 10px;font-weight:800;color:#059669;">0.00</td>
            <td class="fsr-num" id="fpp-total-tds" style="padding:8px 10px;font-weight:700;color:#374151;">0.00</td>
            <td class="fsr-num" id="fpp-total-adv" style="padding:8px 10px;font-weight:700;color:#374151;">0.00</td>
            <td></td></tr>`);

        this.$pending_body.off("change").on("change", ".fpp-tick", function() {
            const idx = parseInt($(this).data("idx"), 10);
            const checked = $(this).prop("checked");
            self.on_tick(idx, checked);
        });
        this.$pending_body.off("input").on("input", ".fpp-pay-input", function() {
            const idx = parseInt($(this).data("idx"), 10);
            const inv = self.pending[idx];
            if (!inv) return;
            const val = self.flt($(this).val());
            inv.pay_amount = val;
            inv._manually_selected = val > 0;
            const $tr = self.pending_body_row(idx);
            if (!$tr.length) return;
            const checked = val > 0;
            if (checked) delete self.deselected[idx];
            else self.deselected[idx] = true;
            $tr.find(".fpp-tick").prop("checked", checked);
            $tr.toggleClass("fpp-checked", checked);
            const $st = $tr.find(".fpp-status-cell");
            if (!checked) $st.html("");
            else if (val >= self.eff(inv) - 0.01) $st.html('<span style="color:#059669;font-weight:700;font-size:11px;"><i class="fa fa-check-circle"></i> Full</span>');
            else $st.html('<span style="color:#b45309;font-weight:700;font-size:11px;"><i class="fa fa-adjust"></i> Partial</span>');
            self.update_selected_total();
        });
        this.$pending_body.off("input.tdsadv").on("input.tdsadv", ".fpp-tds-input, .fpp-adv-input", function() {
            const idx = parseInt($(this).data("idx"), 10);
            const inv = self.pending[idx];
            if (!inv) return;
            const $tr = self.pending_body_row(idx);
            if ($tr.length) {
                inv.tds = self.flt($tr.find(".fpp-tds-input").val());
                inv.advance = self.flt($tr.find(".fpp-adv-input").val());
            }
            self.update_selected_total();
        });
        this.update_selected_total();
    }

    render_carry_banner() {
        const bal = this.flt(this.advance_balance);
        if (bal > 0) {
            const applied = this.flt(this.carry_applied_total);
            this.$carry_banner.show().html(
                `<i class="fa fa-info-circle"></i> Advance balance <b>Rs. ${this.fmt(bal)}</b>` +
                (applied > 0 ? ` &middot; <b>Rs. ${this.fmt(applied)}</b> auto-applied to pending invoices (oldest first)` : " &middot; will auto-apply on payment (oldest first)")
            );
        } else {
            this.$carry_banner.hide();
        }
    }

    pending_body_row(idx) {
        return this.$pending_body.find(`tr[data-idx="${idx}"]`);
    }

    on_tick(idx, checked) {
        const inv = this.pending[idx];
        if (!inv) return;
        if (checked) {
            delete this.deselected[idx];
            inv.pay_amount = this.eff(inv);
            inv._manually_selected = true;
            this.adjust_to_budget();
        } else {
            this.deselected[idx] = true;
            inv.pay_amount = 0;
            inv._manually_selected = false;
            this.auto_fill_from_amount();
        }
        this.render_checks();
        this.update_selected_total();
    }

    adjust_to_budget() {
        const self = this;
        const amount = this.flt(this.$amount.val());
        if (amount <= 0) return;
        let manual_total = 0;
        this.pending.forEach(function(inv) {
            if (inv._manually_selected) manual_total += self.flt(inv.pay_amount);
        });
        let remaining = Math.max(0, amount - manual_total);
        this.pending.forEach(function(inv) {
            if (remaining <= 0.01) return;
            if (inv._manually_selected) return;
            if (self.deselected[inv._idx]) return;
            inv.pay_amount = Math.min(self.eff(inv), remaining);
            remaining -= inv.pay_amount;
        });
        this.pending.forEach(function(inv) {
            if (!inv._manually_selected && !self.deselected[inv._idx] && self.flt(inv.pay_amount) <= 0) return;
        });
    }

    auto_fill_from_amount() {
        const self = this;
        const amount = this.flt(this.$amount.val());
        if (amount <= 0) {
            this.pending.forEach(function(inv) {
                if (!inv._manually_selected) inv.pay_amount = 0;
            });
            this.render_checks();
            this.update_selected_total();
            return;
        }
        let manual_total = 0;
        this.pending.forEach(function(inv) {
            if (!inv._manually_selected) {
                inv.pay_amount = 0;
            } else {
                manual_total += self.flt(inv.pay_amount);
            }
        });
        let remaining = Math.max(0, amount - manual_total);
        this.pending.forEach(function(inv) {
            if (remaining <= 0.01) return;
            if (inv._manually_selected) return;
            if (self.deselected[inv._idx]) return;
            inv.pay_amount = Math.min(self.eff(inv), remaining);
            remaining -= inv.pay_amount;
        });
        this.render_checks();
        this.update_selected_total();
    }

    auto_fill_oldest() {
        const self = this;
        const amount = this.flt(this.$amount.val());
        if (amount <= 0) return;
        let remaining = amount;
        this.pending.forEach(function(inv) {
            if (remaining <= 0.01) return;
            if (self.deselected[inv._idx]) return;
            inv.pay_amount = Math.min(self.eff(inv), remaining);
            remaining -= inv.pay_amount;
        });
        this.render_checks();
        this.update_selected_total();
    }

    render_checks() {
        const self = this;
        this.pending.forEach(function(inv) {
            const $tr = self.pending_body_row(inv._idx);
            if (!$tr.length) return;
            const checked = self.flt(inv.pay_amount) > 0;
            $tr.find(".fpp-tick").prop("checked", checked);
            $tr.find(".fpp-pay-input").val(self.flt(inv.pay_amount) > 0 ? self.flt(inv.pay_amount).toFixed(2) : 0);
            $tr.find(".fpp-tds-input").val(self.flt(inv.tds) > 0 ? self.flt(inv.tds).toFixed(2) : 0);
            $tr.find(".fpp-adv-input").val(self.flt(inv.advance) > 0 ? self.flt(inv.advance).toFixed(2) : 0);
            $tr.toggleClass("fpp-checked", checked);
            const $st = $tr.find(".fpp-status-cell");
            if (self.flt(inv.pay_amount) <= 0) $st.html("");
            else if (self.flt(inv.pay_amount) >= self.eff(inv) - 0.01) $st.html('<span style="color:#059669;font-weight:700;font-size:11px;"><i class="fa fa-check-circle"></i> Full</span>');
            else $st.html('<span style="color:#b45309;font-weight:700;font-size:11px;"><i class="fa fa-adjust"></i> Partial</span>');
        });
    }

    select_all(check) {
        const self = this;
        this.pending.forEach(function(inv) {
            if (check) {
                delete self.deselected[inv._idx];
                inv.pay_amount = self.eff(inv);
            } else {
                self.deselected[inv._idx] = true;
                inv.pay_amount = 0;
            }
        });
        this.render_checks();
        this.update_selected_total();
    }

    deselect_all() {
        this.$amount.val("");
        this.select_all(false);
    }

    update_selected_total() {
        const selected = this.pending.filter(inv => this.flt(inv.pay_amount) > 0);
        const total = selected.reduce((s, inv) => s + this.flt(inv.pay_amount), 0);
        const tds = selected.reduce((s, inv) => s + this.flt(inv.tds), 0);
        const advance = selected.reduce((s, inv) => s + this.flt(inv.advance), 0);
        const carry = selected.reduce((s, inv) => s + this.flt(inv.carry_applied), 0);
        const net = total + advance - tds;
        this.$sel_count.text(selected.length);
        this.$sel_total.text(this.fmt(total));
        if (selected.length) {
            let html = `<b>Bank payment</b> = Invoices <b>Rs. ${this.fmt(total)}</b>`;
            if (advance > 0) html += ` + Advance <b>Rs. ${this.fmt(advance)}</b>`;
            if (tds > 0) html += ` &minus; TDS <b>Rs. ${this.fmt(tds)}</b>`;
            if (carry > 0) html += ` <span style="color:#92400e;">(incl. Rs. ${this.fmt(carry)} auto-applied advance)</span>`;
            html += ` = <b>Rs. ${this.fmt(net)}</b>`;
            this.$net_row.show().html(html);
        } else {
            this.$net_row.hide();
        }
        const base = this.flt(this.total_outstanding);
        const pct = base > 0 ? Math.min(100, (total / base) * 100) : 0;
        this.$progress_bar.css("width", pct.toFixed(1) + "%");
        this.$progress_pct.text(Math.round(pct) + "%");
        this.$progress_label.text("Paying Rs. " + this.fmt(total) + " of Rs. " + this.fmt(base));
        const $toPay = this.$root.find("#fpp-total-to-pay");
        if ($toPay.length) $toPay.text(this.fmt(total));
        const $tTds = this.$root.find("#fpp-total-tds");
        if ($tTds.length) $tTds.text(this.fmt(tds));
        const $tAdv = this.$root.find("#fpp-total-adv");
        if ($tAdv.length) $tAdv.text(this.fmt(advance));
        if (this.pending.length) this.subtitle();
    }

    subtitle() {
        const group_mode = this.is_group_mode();
        const member_count = group_mode ? Object.keys(this.by_party || {}).length : 0;
        let text = "";
        if (this.group) text += "Group: " + this.group + (member_count ? " | " + member_count + " member" + (member_count === 1 ? "" : "s") : "") + " | ";
        text += this.pending.length + " invoice" + (this.pending.length === 1 ? "" : "s") + " | Total Outstanding: Rs. " + this.fmt(this.total_outstanding);
        if (this.flt(this.advance_balance) > 0) text += " | Advance bal: Rs. " + this.fmt(this.advance_balance);
        const total = this.pending.filter(inv => this.flt(inv.pay_amount) > 0).reduce((s, inv) => s + this.flt(inv.pay_amount), 0);
        if (total > 0) text += " | To Pay: Rs. " + this.fmt(total);
        this.$root.find("#fpp-pending-sub").text(text);
    }

    create_payment() {
        const self = this;
        const group_mode = this.is_group_mode();
        const company = this.$company.val();
        const party = this.$supplier.val();
        const errors = [];
        if (!company) errors.push("Company is required");
        if (!party) errors.push("Supplier is required");
        if (!this.pending.some(inv => this.flt(inv.pay_amount) > 0)) errors.push("Select at least one invoice to pay");
        this.pending.forEach(function(inv) {
            if (self.flt(inv.pay_amount) > 0 && self.flt(inv.tds) > self.eff(inv) + 0.01) {
                errors.push("TDS for " + inv.name + " exceeds its outstanding (Rs. " + self.fmt(self.eff(inv)) + ")");
            }
        });
        if (errors.length) { frappe.msgprint({ title: "Validation Error", indicator: "red", message: errors.join("<br>") }); return; }

        this.$status_bar.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Creating Payment Entries...</span>');
        this.$root.find("#fpp-create").prop("disabled", true);
        if (group_mode) {
            const by_party = {};
            this.pending.forEach(function(inv) {
                if (self.flt(inv.pay_amount) <= 0) return;
                const p = inv.supplier || "";
                if (!p) return;
                if (!by_party[p]) by_party[p] = { party: p, pay_amount: 0, invoices: [] };
                by_party[p].pay_amount += self.flt(inv.pay_amount);
                by_party[p].invoices.push({ name: inv.name, pay_amount: self.flt(inv.pay_amount), tds: self.flt(inv.tds), advance: self.flt(inv.advance) });
            });
            const items = Object.keys(by_party).map(k => by_party[k]);
            frappe.call({
                method: "fast_entry_app.api.payment.create_party_group_payment",
                args: { data: {
                    company: company,
                    party_type: "Supplier",
                    group: party,
                    posting_date: this.$posting_date.val() || "",
                    mode_of_payment: this.$mode.val() || "",
                    reference_no: this.$ref_no.val() || "",
                    items: items,
                } },
                callback: function(r) {
                    self.$root.find("#fpp-create").prop("disabled", false);
                    const m = r.message || {};
                    if (m.name) {
                        let html = '<i class="fa fa-check-circle" style="color:#059669;"></i> Group payment <b><a href="/app/party-group-payment/' + m.name + '" target="_blank">' + m.name + '</a></b> created for group <b>' + self.esc(m.group_name || m.group || "") + '</b> for total Rs. ' + self.fmt(m.total) + ':';
                        html += "<ul style='margin:6px 0 0 18px;'>";
                        (m.payments || []).forEach(function(p) {
                            html += `<li><b>${self.esc(p.party_name || p.party)}</b> &rarr; <a href="/app/payment-entry/${p.payment_entry}" target="_blank">${p.payment_entry}</a> &mdash; Rs. ${self.fmt(p.paid_amount)} (${p.invoice_count} invoice${p.invoice_count === 1 ? "" : "s"})</li>`;
                        });
                        html += "</ul>";
                        self.$result.html(html).show();
                        self.$status_bar.html('<span class="fe-status-ok"><i class="fa fa-check"></i> Group payment created</span>');
                        self.load_pending();
                    } else {
                        self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Group payment not created</span>');
                    }
                },
                error: function(err) {
                    self.$root.find("#fpp-create").prop("disabled", false);
                    let msg = "Failed to create group payment";
                    if (err && err.message && err.message.exc_type) { try { msg = JSON.parse(err.message._server_messages || "[]").join(" ") || msg; } catch (e) {} }
                    self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> ' + msg + '</span>');
                }
            });
            return;
        }
        const items = this.pending.filter(inv => this.flt(inv.pay_amount) > 0).map(function(inv) {
            return { name: inv.name, supplier: inv.supplier, pay_amount: self.flt(inv.pay_amount), tds: self.flt(inv.tds), advance: self.flt(inv.advance) };
        });
        this.$status_bar.html('<span class="fe-status-ok"><i class="fa fa-check"></i> ...</span>');
        this.$root.find("#fpp-create").prop("disabled", true);
        frappe.call({
            method: "fast_entry_app.api.payment.create_bulk_supplier_payment",
            args: {
                data: {
                    company: company,
                    posting_date: this.$posting_date.val() || "",
                    mode_of_payment: this.$mode.val() || "",
                    reference_no: this.$ref_no.val() || "",
                    items: items,
                },
            },
            callback: function(r) {
                self.$root.find("#fpp-create").prop("disabled", false);
                if (r.message && r.message.count) {
                    const m = r.message;
                    let html = '<i class="fa fa-check-circle" style="color:#059669;"></i> Created <b>' + m.count + '</b> Payment ' + (m.count > 1 ? "Entries" : "Entry") + ' for total Rs. ' + self.fmt(m.total) + ':';
                    html += "<ul style='margin:6px 0 0 18px;'>";
                    (m.payments || []).forEach(function(p) {
                        html += `<li><b>${p.supplier_name}</b> (${p.supplier}) &rarr; <a href="/app/payment-entry/${p.payment_entry}" target="_blank">${p.payment_entry}</a> &mdash; Rs. ${self.fmt(p.amount)}</li>`;
                    });
                    html += "</ul>";
                    self.$result.html(html).show();
                    self.$status_bar.html('<span class="fe-status-ok"><i class="fa fa-check"></i> Payment entries created</span>');
                    self.load_pending();
                } else {
                    self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Payment entries not created</span>');
                }
            },
            error: function(err) {
                self.$root.find("#fpp-create").prop("disabled", false);
                let msg = "Failed to create payment entries";
                if (err && err.message && err.message.exc_type) { try { msg = JSON.parse(err.message._server_messages || "[]").join(" ") || msg; } catch (e) {} }
                self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> ' + msg + '</span>');
            }
        });
    }
};