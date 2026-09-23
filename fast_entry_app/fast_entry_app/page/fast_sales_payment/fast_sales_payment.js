frappe.provide("fast_entry_app");

frappe.pages["fast-sales-payment"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Fast Sales Payment"), single_column: true });
    fast_entry_app.sales_payment_page = new fast_entry_app.SalesPayment(wrapper);
};

fast_entry_app.SalesPayment = class SalesPayment {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.pending = [];
        this.deselected = {};
        this.build();
    }

    flt(v) { return parseFloat(v) || 0; }
    fmt(v) { return (this.flt(v)).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }

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
                    <div class="fe-field"><label>Company <span class="reqd">*</span></label><select class="fe-input" id="fsp-company"></select></div>
                    <div class="fe-field fe-field-wide"><label>Customer <span class="reqd">*</span></label><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-input" id="fsp-customer" placeholder="Search customer..." autocomplete="off" /></div></div>
                    <div class="fe-field" style="flex:0 0 120px;align-self:flex-end;"><button class="fe-btn fe-btn-primary" id="fsp-load" style="width:100%;justify-content:center;"><i class="fa fa-search"></i> Load</button></div>
                </div>
                <div class="fe-header-row">
                    <div class="fe-field"><label>Posting Date</label><input type="date" class="fe-input" id="fsp-posting-date" value="${today}" /></div>
                    <div class="fe-field"><label>Mode of Payment</label><select class="fe-input" id="fsp-mode"></select></div>
                    <div class="fe-field"><label>Reference No</label><input type="text" class="fe-input" id="fsp-ref-no" placeholder="Optional" /></div>
                </div>
            </div>

            <div class="fe-card">
                <div class="fe-card-header"><i class="fa fa-file-text-o"></i> Pending Sales Invoices <span class="fsr-summary-sub" id="fsp-pending-sub"></span></div>
                <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;margin-bottom:10px;">
                    <div class="fe-field"><label>Received Amount (Rs)</label><input type="number" class="fe-input" id="fsp-amount" min="0" step="0.01" placeholder="Auto-fill oldest first" /></div>
                    <div style="flex:0 0 190px;"><button class="fe-btn fe-btn-sm" id="fsp-pay-all" style="width:100%;justify-content:center;height:36px;"><i class="fa fa-check-circle"></i> Select All Full</button></div>
                    <div style="flex:0 0 190px;"><button class="fe-btn fe-btn-sm" id="fsp-deselect-all" style="width:100%;justify-content:center;height:36px;"><i class="fa fa-times-circle"></i> Deselect All</button></div>
                </div>
                <div id="fsp-pending-wrap" style="overflow-x:auto;">
                    <table class="fsr-table" id="fsp-pending-table">
                        <thead><tr>
                            <th style="width:36px;"></th>
                            <th>Invoice</th>
                            <th>Date</th>
                            <th>Customer</th>
                            <th class="fsr-num">Grand Total (Rs)</th>
                            <th class="fsr-num">Outstanding (Rs)</th>
                            <th class="fsr-num">To Pay (Rs)</th>
                            <th>Status</th>
                        </tr></thead>
                        <tbody id="fsp-pending-body"></tbody>
                        <tfoot id="fsp-pending-total"></tfoot>
                    </table>
                </div>
                <div class="fsr-empty" id="fsp-pending-empty" style="display:none;">No pending sales invoices for this customer / group.</div>
            </div>

            <div class="fe-card">
                <div class="fe-card-header"><i class="fa fa-money"></i> Payment Details</div>
                <div class="fsp-progress" style="margin-bottom:10px;">
                    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
                        <span id="fsp-progress-label" style="color:#374151;">Paying Rs. 0.00 of Rs. 0.00</span>
                        <span id="fsp-progress-pct" style="font-weight:700;color:#059669;">0%</span>
                    </div>
                    <div style="height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden;">
                        <div id="fsp-progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#059669,#10b981);border-radius:4px;transition:width 0.3s;"></div>
                    </div>
                </div>
                <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;">
                    <div class="fe-field"><label>Selected Invoices</label><span id="fsp-sel-count" style="font-weight:700;">0</span></div>
                    <div class="fe-field"><label>Total To Receive (Rs)</label><span class="fsp-selected-total" id="fsp-sel-total" style="font-size:16px;">0.00</span></div>
                    <div class="fe-field" style="flex:0 0 260px;align-self:flex-end;"><button class="fe-btn fe-btn-success" id="fsp-create" style="width:100%;justify-content:center;"><i class="fa fa-check"></i> Create Payment Entry</button></div>
                </div>
                <div class="fsr-empty" id="fsp-result" style="display:none;padding:8px 0;text-align:left;"></div>
            </div>

            <div class="fe-status-bar" id="fsp-status-bar"></div>
        </div>`;
    }

    bind_elements() {
        const self = this;
        this.$company = this.$root.find("#fsp-company");
        this.$customer = this.$root.find("#fsp-customer");
        this.$posting_date = this.$root.find("#fsp-posting-date");
        this.$mode = this.$root.find("#fsp-mode");
        this.$ref_no = this.$root.find("#fsp-ref-no");
        this.$amount = this.$root.find("#fsp-amount");
        this.$pending_body = this.$root.find("#fsp-pending-body");
        this.$pending_total = this.$root.find("#fsp-pending-total");
        this.$pending_empty = this.$root.find("#fsp-pending-empty");
        this.$status_bar = this.$root.find("#fsp-status-bar");
        this.$sel_count = this.$root.find("#fsp-sel-count");
        this.$sel_total = this.$root.find("#fsp-sel-total");
        this.$progress_bar = this.$root.find("#fsp-progress-bar");
        this.$progress_pct = this.$root.find("#fsp-progress-pct");
        this.$progress_label = this.$root.find("#fsp-progress-label");
        this.$result = this.$root.find("#fsp-result");

        this.$company.on("change", () => {
            localStorage.setItem("fsp_company", this.$company.val());
            this.deselect_all();
        });
        this.$customer.on("change", () => this.deselect_all());
        this.$posting_date.on("change", () => this.deselect_all());
        this.$root.find("#fsp-load").on("click", () => this.load_pending());
        this.$root.find("#fsp-pay-all").on("click", () => {
            this.$amount.val(this.total_outstanding || 0);
            this.select_all(true);
        });
        this.$root.find("#fsp-deselect-all").on("click", () => { this.$amount.val(""); this.select_all(false); });
        let timer = null;
        this.$amount.on("input", function() {
            clearTimeout(timer);
            timer = setTimeout(() => {
                self.auto_fill_from_amount();
            }, 120);
        });
        this.$root.find("#fsp-create").on("click", () => this.create_payment());

        this.bind_customer_autocomplete();
    }

    bind_customer_autocomplete() {
        const self = this;
        let timer = null;
        this.$customer.on("input", function() {
            clearTimeout(timer);
            const val = $(this).val();
            if (val.length < 1) { self.hide_dropdown(); return; }
            timer = setTimeout(() => {
                frappe.call({
                    method: "fast_entry_app.api.party.search_customers",
                    args: { search: val, company: self.$company.val() || "", limit: 12 },
                    callback: function(r) {
                        const items = r.message || [];
                        if (!items.length) { self.hide_dropdown(); return; }
                        self._ac_items = items;
                        let html = "";
                        items.forEach(function(c) {
                            const sec = c.fe_group ? c.fe_group + " | " + c.name : c.name;
                            html += `<div class="fe-dropdown-item" data-code="${c.name}"><span class="fe-dd-primary">${c.customer_name || c.name}</span><span class="fe-dd-secondary">${sec}</span></div>`;
                        });
                        self.show_dropdown(self.$customer, html, function($el) {
                            const picked = (self._ac_items || []).find(i => i.name === $el.data("code")) || {};
                            self.$customer.val(picked.name).attr("data-party-name", picked.customer_name || picked.name);
                        });
                    },
                });
            }, 200);
        });
        this.$customer.on("keydown", function(e) {
            if (!self.$dd) return;
            const $items = self.$dd.find(".fe-dropdown-item");
            const $active = $items.filter(".active");
            if (e.key === "ArrowDown") { e.preventDefault(); if (!$active.length) $items.first().addClass("active"); else { $active.removeClass("active").next().addClass("active"); } }
            else if (e.key === "ArrowUp") { e.preventDefault(); if (!$active.length) $items.last().addClass("active"); else { $active.removeClass("active").prev().addClass("active"); } }
            else if (e.key === "Enter") { e.preventDefault(); if ($active.length) $active.trigger("mousedown"); }
            else if (e.key === "Escape") { self.hide_dropdown(); }
        });
        this.$customer.on("blur", () => setTimeout(() => this.hide_dropdown(), 150));
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
                const ls = localStorage.getItem("fsp_company");
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
        const customer = this.$customer.val();
        const self = this;
        if (!company || !customer) { frappe.msgprint({ title: "Missing Details", indicator: "orange", message: "Select company and customer first." }); return; }
        this.$pending_body.html(`<tr><td colspan="8" style="text-align:center;padding:20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin"></i> Loading pending invoices...</td></tr>`);
        this.$pending_total.html("");
        this.$pending_empty.hide();
        this.$result.hide();
        frappe.call({
            method: "fast_entry_app.api.payment.get_pending_sales_invoices",
            args: { company: company, customer: customer },
            callback: function(r) {
                const data = r.message || {};
                self.pending = (data.invoices || []).map(function(inv, i) {
                    inv._idx = i;
                    return inv;
                });
                self.group = data.group || "";
                self.deselected = {};
                self.total_outstanding = self.flt(data.total_outstanding);
                self.render_pending();
            },
            error: function() { self.$pending_body.html(`<tr><td colspan="8" style="text-align:center;padding:20px;color:#ef4444;">Failed to load pending invoices.</td></tr>`); }
        });
    }

    render_pending() {
        const self = this;
        this.$pending_body.empty();
        this.$pending_total.html("");
        this.$amount.val("");
        if (!this.pending.length) { this.$pending_empty.show(); this.$root.find("#fsp-pending-sub").text(""); this.update_selected_total(); return; }
        this.$pending_empty.hide();
        this.$root.find("#fsp-pending-sub").text(
            (this.group ? "Group: " + this.group + " | " : "") + this.pending.length + " invoices | Total Outstanding: Rs. " + this.fmt(this.total_outstanding)
        );

        this.pending.forEach(function(inv) {
            const tr = document.createElement("tr");
            tr.dataset.idx = inv._idx;
            tr.innerHTML = `
                <td><input type="checkbox" class="fe-input fsp-tick" data-idx="${inv._idx}" /></td>
                <td><a href="/app/sales-invoice/${inv.name}" target="_blank">${inv.name}</a></td>
                <td class="fsr-date">${inv.posting_date}</td>
                <td>${inv.customer_name}${inv.customer !== self.$customer.val() ? ' <span style="color:#9ca3af;font-size:11px;">(' + inv.customer + ')</span>' : ""}</td>
                <td class="fsr-num">${self.fmt(inv.grand_total)}</td>
                <td class="fsr-num" style="font-weight:700;color:#dc2626;">${self.fmt(inv.outstanding_amount)}</td>
                <td class="fsr-num"><input type="number" class="fe-input fsp-pay-input" data-idx="${inv._idx}" min="0" step="0.01" value="0" /></td>
                <td class="fsp-status-cell"></td>`;
            self.$pending_body[0].appendChild(tr);
        });
        this.$pending_total.html(`<tr style="background:#f9fafb;border-top:2px solid #e5e7eb;">
            <td colspan="5" style="padding:8px 10px;font-weight:700;color:#374151;">Total Outstanding</td>
            <td class="fsr-num" style="padding:8px 10px;font-weight:800;color:#dc2626;">${self.fmt(this.total_outstanding)}</td>
            <td class="fsr-num" id="fsp-total-to-pay" style="padding:8px 10px;font-weight:800;color:#059669;">0.00</td>
            <td></td></tr>`);

        this.$pending_body.off("change").on("change", ".fsp-tick", function() {
            const idx = parseInt($(this).data("idx"), 10);
            self.on_tick(idx, $(this).prop("checked"));
        });
        this.$pending_body.off("input").on("input", ".fsp-pay-input", function() {
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
            $tr.find(".fsp-tick").prop("checked", checked);
            $tr.toggleClass("fsp-checked", checked);
            const $st = $tr.find(".fsp-status-cell");
            if (!checked) $st.html("");
            else if (val >= self.flt(inv.outstanding_amount) - 0.01) $st.html('<span style="color:#059669;font-weight:700;font-size:11px;"><i class="fa fa-check-circle"></i> Full</span>');
            else $st.html('<span style="color:#b45309;font-weight:700;font-size:11px;"><i class="fa fa-adjust"></i> Partial</span>');
            self.update_selected_total();
        });
        this.update_selected_total();
    }

    pending_body_row(idx) {
        return this.$pending_body.find(`tr[data-idx="${idx}"]`);
    }

    on_tick(idx, checked) {
        const inv = this.pending[idx];
        if (!inv) return;
        if (checked) {
            delete this.deselected[idx];
            inv.pay_amount = this.flt(inv.outstanding_amount);
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
            inv.pay_amount = Math.min(self.flt(inv.outstanding_amount), remaining);
            remaining -= inv.pay_amount;
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
            inv.pay_amount = Math.min(self.flt(inv.outstanding_amount), remaining);
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
            inv.pay_amount = Math.min(self.flt(inv.outstanding_amount), remaining);
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
            $tr.find(".fsp-tick").prop("checked", checked);
            $tr.find(".fsp-pay-input").val(self.flt(inv.pay_amount) > 0 ? self.flt(inv.pay_amount).toFixed(2) : 0);
            $tr.toggleClass("fsp-checked", checked);
            const $st = $tr.find(".fsp-status-cell");
            if (self.flt(inv.pay_amount) <= 0) $st.html("");
            else if (self.flt(inv.pay_amount) >= self.flt(inv.outstanding_amount) - 0.01) $st.html('<span style="color:#059669;font-weight:700;font-size:11px;"><i class="fa fa-check-circle"></i> Full</span>');
            else $st.html('<span style="color:#b45309;font-weight:700;font-size:11px;"><i class="fa fa-adjust"></i> Partial</span>');
        });
    }

    select_all(check) {
        const self = this;
        this.pending.forEach(function(inv) {
            if (check) {
                delete self.deselected[inv._idx];
                inv.pay_amount = self.flt(inv.outstanding_amount);
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
        this.$sel_count.text(selected.length);
        this.$sel_total.text(this.fmt(total));
        const base = this.flt(this.total_outstanding);
        const pct = base > 0 ? Math.min(100, (total / base) * 100) : 0;
        this.$progress_bar.css("width", pct.toFixed(1) + "%");
        this.$progress_pct.text(Math.round(pct) + "%");
        this.$progress_label.text("Paying Rs. " + this.fmt(total) + " of Rs. " + this.fmt(base));
        const $toPay = this.$root.find("#fsp-total-to-pay");
        if ($toPay.length) $toPay.text(this.fmt(total));
        if (this.pending.length) {
            this.$root.find("#fsp-pending-sub").text(
                (this.group ? "Group: " + this.group + " | " : "") +
                this.pending.length + " invoices | Total Outstanding: Rs. " + this.fmt(this.total_outstanding) +
                (total > 0 ? " | To Pay: Rs. " + this.fmt(total) : "")
            );
        }
    }

    create_payment() {
        const self = this;
        const company = this.$company.val();
        const customer = this.$customer.val();
        const items = this.pending.filter(inv => this.flt(inv.pay_amount) > 0).map(function(inv) {
            return { name: inv.name, customer: inv.customer, pay_amount: self.flt(inv.pay_amount) };
        });
        const errors = [];
        if (!company) errors.push("Company is required");
        if (!customer) errors.push("Customer is required");
        if (!items.length) errors.push("Select at least one invoice to pay");
        if (errors.length) { frappe.msgprint({ title: "Validation Error", indicator: "red", message: errors.join("<br>") }); return; }

        this.$status_bar.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Creating Payment Entries...</span>');
        this.$root.find("#fsp-create").prop("disabled", true);
        frappe.call({
            method: "fast_entry_app.api.payment.create_bulk_customer_payment",
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
                self.$root.find("#fsp-create").prop("disabled", false);
                if (r.message && r.message.count) {
                    const m = r.message;
                    let html = '<i class="fa fa-check-circle" style="color:#059669;"></i> Created <b>' + m.count + '</b> Payment ' + (m.count > 1 ? "Entries" : "Entry") + ' for total Rs. ' + self.fmt(m.total) + ':';
                    html += "<ul style='margin:6px 0 0 18px;'>";
                    (m.payments || []).forEach(function(p) {
                        html += `<li><b>${p.customer_name}</b> (${p.customer}) &rarr; <a href="/app/payment-entry/${p.payment_entry}" target="_blank">${p.payment_entry}</a> &mdash; Rs. ${self.fmt(p.amount)}</li>`;
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
                self.$root.find("#fsp-create").prop("disabled", false);
                let msg = "Failed to create payment entries";
                if (err && err.message && err.message.exc_type) { try { msg = JSON.parse(err.message._server_messages || "[]").join(" ") || msg; } catch (e) {} }
                self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> ' + msg + '</span>');
            }
        });
    }
};