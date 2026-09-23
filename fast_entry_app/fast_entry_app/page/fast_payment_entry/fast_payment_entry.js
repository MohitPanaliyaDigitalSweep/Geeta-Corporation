frappe.provide("fast_entry_app");

frappe.pages["fast-payment-entry"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Fast Payment Entry"), single_column: true });
    fast_entry_app.payment_entry_page = new fast_entry_app.PaymentEntry(wrapper);
};

fast_entry_app.PaymentEntry = class PaymentEntry {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.pending = [];
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
                    <div class="fe-field"><label>Company <span class="reqd">*</span></label><select class="fe-input" id="fpe-company"></select></div>
                    <div class="fe-field"><label>Party Type <span class="reqd">*</span></label>
                        <select class="fe-input" id="fpe-party-type">
                            <option value="Customer">Customer (Receive)</option>
                            <option value="Supplier">Supplier (Pay)</option>
                        </select>
                    </div>
                    <div class="fe-field fe-field-wide"><label>Party <span class="reqd">*</span></label><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-input" id="fpe-party" placeholder="Search customer / supplier..." autocomplete="off" /></div></div>
                    <div class="fe-field" style="flex:0 0 120px;align-self:flex-end;"><button class="fe-btn fe-btn-primary" id="fpe-load" style="width:100%;justify-content:center;"><i class="fa fa-search"></i> Load</button></div>
                </div>
                <div class="fe-header-row">
                    <div class="fe-field"><label>Posting Date</label><input type="date" class="fe-input" id="fpe-posting-date" value="${today}" /></div>
                    <div class="fe-field"><label>Mode of Payment</label><select class="fe-input" id="fpe-mode"></select></div>
                    <div class="fe-field"><label>Reference No</label><input type="text" class="fe-input" id="fpe-ref-no" placeholder="Optional" /></div>
                    <div class="fe-field"><label>Reference Date</label><input type="date" class="fe-input" id="fpe-ref-date" value="${today}" /></div>
                </div>
            </div>

            <div class="fe-card">
                <div class="fe-card-header"><i class="fa fa-file-text-o"></i> Pending Invoices <span class="fsr-summary-sub" id="fpe-pending-sub"></span></div>
                <div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:10px;">
                    <div class="fe-field"><label>Amount to Pay (Rs) <span class="reqd">*</span></label><input type="number" class="fe-input" id="fpe-amount" min="0" step="0.01" placeholder="Auto-fill oldest first" /></div>
                    <div class="fe-field" style="flex:0 0 190px;align-self:flex-end;"><button class="fe-btn fe-btn-sm" id="fpe-pay-all" style="width:100%;justify-content:center;"><i class="fa fa-check-circle"></i> Select All Full</button></div>
                    <div class="fe-field" style="flex:0 0 190px;align-self:flex-end;"><button class="fe-btn fe-btn-sm" id="fpe-deselect-all" style="width:100%;justify-content:center;"><i class="fa fa-times-circle"></i> Deselect All</button></div>
                </div>
                <div id="fpe-pending-wrap" style="overflow-x:auto;">
                    <table class="fsr-table" id="fpe-pending-table">
                        <thead><tr>
                            <th style="width:36px;"></th>
                            <th>Invoice</th>
                            <th>Date</th>
                            <th>Due Date</th>
                            <th class="fsr-num">Grand Total (Rs)</th>
                            <th class="fsr-num">Outstanding (Rs)</th>
                            <th class="fsr-num">To Pay (Rs)</th>
                            <th>Status</th>
                        </tr></thead>
                        <tbody id="fpe-pending-body"></tbody>
                        <tfoot id="fpe-pending-total"></tfoot>
                    </table>
                </div>
                <div class="fsr-empty" id="fpe-pending-empty" style="display:none;">No pending invoices for this party.</div>
            </div>

            <div class="fe-card">
                <div class="fe-card-header"><i class="fa fa-money"></i> Payment Details</div>
                <div style="margin-bottom:10px;">
                    <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px;">
                        <span id="fpe-progress-label" style="color:#374151;">Paying Rs. 0.00 of Rs. 0.00</span>
                        <span id="fpe-progress-pct" style="font-weight:700;color:#059669;">0%</span>
                    </div>
                    <div style="height:8px;background:#e5e7eb;border-radius:4px;overflow:hidden;">
                        <div id="fpe-progress-bar" style="height:100%;width:0%;background:linear-gradient(90deg,#059669,#10b981);border-radius:4px;transition:width 0.3s;"></div>
                    </div>
                </div>
                <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;">
                    <div class="fe-field"><label>Selected Invoices</label><span id="fpe-sel-count" style="font-weight:700;">0</span></div>
                    <div class="fe-field"><label>Total To Pay (Rs)</label><span id="fpe-sel-total" style="font-size:16px;font-weight:700;">0.00</span></div>
                    <div class="fe-field" style="flex:0 0 260px;align-self:flex-end;"><button class="fe-btn fe-btn-success" id="fpe-create" style="width:100%;justify-content:center;"><i class="fa fa-check"></i> Create Payment Entry</button></div>
                </div>
                <div class="fsr-empty" id="fpe-allocation-warn" style="display:none;padding:8px 0;text-align:left;color:#92400e;"></div>
            </div>

            <div class="fe-status-bar" id="fpe-status-bar"></div>
        </div>`;
    }

    bind_elements() {
        const self = this;
        this.$company = this.$root.find("#fpe-company");
        this.$party_type = this.$root.find("#fpe-party-type");
        this.$party = this.$root.find("#fpe-party");
        this.$amount = this.$root.find("#fpe-amount");
        this.$mode = this.$root.find("#fpe-mode");
        this.$posting_date = this.$root.find("#fpe-posting-date");
        this.$ref_no = this.$root.find("#fpe-ref-no");
        this.$ref_date = this.$root.find("#fpe-ref-date");
        this.$pending_body = this.$root.find("#fpe-pending-body");
        this.$pending_total = this.$root.find("#fpe-pending-total");
        this.$pending_empty = this.$root.find("#fpe-pending-empty");
        this.$status_bar = this.$root.find("#fpe-status-bar");
        this.$sel_count = this.$root.find("#fpe-sel-count");
        this.$sel_total = this.$root.find("#fpe-sel-total");
        this.$progress_bar = this.$root.find("#fpe-progress-bar");
        this.$progress_pct = this.$root.find("#fpe-progress-pct");
        this.$progress_label = this.$root.find("#fpe-progress-label");

        this.$company.on("change", () => localStorage.setItem("fpe_company", this.$company.val()));
        this.$party_type.on("change", () => { this.$party.val(""); this.hide_dropdown(); this.deselect_all(); });

        this.$root.find("#fpe-load").on("click", () => this.load_pending());
        this.$root.find("#fpe-pay-all").on("click", () => {
            this.$amount.val(this.total_outstanding || 0);
            this.select_all(true);
        });
        this.$root.find("#fpe-deselect-all").on("click", () => { this.$amount.val(""); this.select_all(false); });
        this.$amount.on("input", () => this.preview_allocation());
        this.$root.find("#fpe-create").on("click", () => this.create_payment());

        this.bind_autocomplete(this.$party, (val, cb) => {
            const pt = this.$party_type.val();
            frappe.call({ method: "fast_entry_app.api.ledger_pnl.search_parties", args: { party_type: pt, search: val, limit: 12 }, callback: (r) => cb(r.message || []) });
        }, (item) => {
            this.$party.val(item.name).attr("data-party-name", item.customer_name || item.supplier_name || item.name);
        }, "name", "name");
    }

    bind_autocomplete($input, search_fn, select_fn, primary_field) {
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
                        html += `<div class="fe-dropdown-item" data-code="${item.name}"><span class="fe-dd-primary">${primary}</span><span class="fe-dd-secondary">${item.name}</span></div>`;
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
                const ls = localStorage.getItem("fpe_company");
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
        const party_type = this.$party_type.val();
        const party = this.$party.val();
        const self = this;
        if (!company || !party) { frappe.msgprint({ title: "Missing Details", indicator: "orange", message: "Select company and party first." }); return; }
        this.$pending_body.html(`<tr><td colspan="7" style="text-align:center;padding:20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin"></i> Loading pending invoices...</td></tr>`);
        this.$pending_total.html("");
        this.$pending_empty.hide();
        frappe.call({
            method: "fast_entry_app.api.payment.get_pending_invoices",
            args: { company: company, party_type: party_type, party: party },
            callback: function(r) {
                const data = r.message || {};
                self.pending = data.invoices || [];
                self.total_outstanding = self.flt(data.total_outstanding);
                self.render_pending();
                self.preview_allocation();
            },
            error: function() { self.$pending_body.html(`<tr><td colspan="7" style="text-align:center;padding:20px;color:#ef4444;">Failed to load pending invoices.</td></tr>`); }
        });
    }

    render_pending() {
        const self = this;
        this.$pending_body.empty();
        this.$pending_total.html("");
        if (!this.pending.length) { this.$pending_empty.show(); this.$root.find("#fpe-pending-sub").text(""); return; }
        this.$pending_empty.hide();
        this.$root.find("#fpe-pending-sub").text(`${this.pending.length} invoices | Total Outstanding: Rs. ${this.fmt(this.total_outstanding)}`);

        this.pending.forEach(function(inv, i) {
            const tr = document.createElement("tr");
            tr.dataset.idx = i;
            const doctype = self.$party_type.val() === "Customer" ? "sales-invoice" : "purchase-invoice";
            tr.innerHTML = `
                <td style="text-align:center;"><input type="checkbox" class="fpe-check" data-idx="${i}" ${i === 0 ? "checked" : ""} /></td>
                <td><a href="/app/${doctype}/${inv.name}" target="_blank">${inv.name}</a></td>
                <td class="fsr-date">${inv.posting_date}</td>
                <td class="fsr-date">${inv.due_date || ""}</td>
                <td class="fsr-num">${self.fmt(inv.grand_total)}</td>
                <td class="fsr-num" style="font-weight:700;color:#dc2626;">${self.fmt(inv.outstanding_amount)}</td>
                <td class="fsr-num fpe-alloc-amt"></td>
                <td class="fpe-alloc-label"></td>`;
            self.$pending_body[0].appendChild(tr);
        });

        this.$pending_body.find(".fpe-check").on("change", () => self.preview_allocation());

        this.$pending_total.html(`<tr style="background:#f9fafb;border-top:2px solid #e5e7eb;">
            <td colspan="5" style="padding:8px 10px;font-weight:700;color:#374151;">Total Outstanding</td>
            <td class="fsr-num" style="padding:8px 10px;font-weight:800;color:#dc2626;">${self.fmt(this.total_outstanding)}</td>
            <td colspan="2"></td></tr>`);

        this.preview_allocation();
    }

    select_all(select) {
        const self = this;
        this.$pending_body.find(".fpe-check").prop("checked", select);
        this.preview_allocation();
    }

    deselect_all() {
        this.pending = [];
        this.$pending_body.empty();
        this.$pending_total.html("");
        this.$pending_empty.show();
        this.$root.find("#fpe-pending-sub").text("");
        this.$sel_count.text("0");
        this.$sel_total.text("0.00");
        this.$progress_bar.css("width", "0%");
        this.$progress_pct.text("0%");
        this.$progress_label.text("Paying Rs. 0.00 of Rs. 0.00");
    }

    preview_allocation() {
        const self = this;
        const amount = this.flt(this.$amount.val());
        const total_outstanding = this.total_outstanding || 0;
        const warn = this.$root.find("#fpe-allocation-warn");
        if (!this.pending.length) return;

        let remaining = amount;
        let total_alloc = 0;
        let selected_count = 0;
        const per = {};

        this.pending.forEach(function(inv, i) {
            const $tr = self.$pending_body.find(`tr[data-idx="${i}"]`);
            const checked = $tr.find(".fpe-check").is(":checked");
            if (!checked || remaining <= 0.01) { per[i] = null; return; }
            selected_count++;
            const alloc = Math.min(self.flt(inv.outstanding_amount), remaining);
            per[i] = alloc;
            remaining -= alloc;
            total_alloc += alloc;
        });
        const excess = amount - total_alloc;

        this.pending.forEach(function(inv, i) {
            const $tr = self.$pending_body.find(`tr[data-idx="${i}"]`);
            if (!$tr.length) return;
            const alloc = per[i];
            const $label = $tr.find(".fpe-alloc-label");
            const $amt = $tr.find(".fpe-alloc-amt");
            if (alloc === null) {
                $label.html('<span style="color:#9ca3af;font-size:11px;">Not paid</span>');
                $amt.text("");
            } else if (alloc >= self.flt(inv.outstanding_amount) - 0.01) {
                $label.html('<span style="color:#059669;font-weight:700;font-size:11px;"><i class="fa fa-check-circle"></i> Full</span>');
                $amt.text(self.fmt(alloc));
            } else {
                $label.html('<span style="color:#b45309;font-weight:700;font-size:11px;"><i class="fa fa-adjust"></i> Partial</span>');
                $amt.text(self.fmt(alloc));
            }
        });

        this.$sel_count.text(selected_count);
        this.$sel_total.text(self.fmt(total_alloc));

        const pct = total_outstanding > 0 ? Math.min(100, (total_alloc / total_outstanding) * 100) : 0;
        this.$progress_bar.css("width", pct + "%");
        this.$progress_pct.text(Math.round(pct) + "%");
        this.$progress_label.text(`Paying Rs. ${self.fmt(total_alloc)} of Rs. ${self.fmt(total_outstanding)}`);

        if (excess > 0.01) {
            warn.html(`<i class="fa fa-exclamation-triangle"></i> Rs. ${this.fmt(excess)} cannot be allocated (no more pending invoices). The Payment Entry will be created for Rs. ${this.fmt(total_alloc)}.`);
            warn.show();
        } else {
            warn.hide();
        }
    }

    create_payment() {
        const self = this;
        const company = this.$company.val();
        const party_type = this.$party_type.val();
        const party = this.$party.val();
        const amount = this.flt(this.$amount.val());
        const errors = [];
        if (!company) errors.push("Company is required");
        if (!party) errors.push("Party is required");
        if (!amount || amount <= 0) errors.push("Amount must be greater than 0");
        if (errors.length) { frappe.msgprint({ title: "Validation Error", indicator: "red", message: errors.join("<br>") }); return; }

        this.$status_bar.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Creating Payment Entry...</span>');
        this.$root.find("#fpe-create").prop("disabled", true);
        frappe.call({
            method: "fast_entry_app.api.payment.create_bulk_payment",
            args: {
                company: company,
                party_type: party_type,
                party: party,
                amount: amount,
                mode_of_payment: this.$mode.val() || "",
                posting_date: this.$posting_date.val() || "",
                reference_no: this.$ref_no.val() || "",
                reference_date: this.$ref_date.val() || "",
            },
            callback: function(r) {
                self.$root.find("#fpe-create").prop("disabled", false);
                if (r.message && r.message.name) {
                    const m = r.message;
                    const fully_paid = (m.allocation || []).filter(a => a.fully_paid).length;
                    const partial = (m.allocation || []).filter(a => !a.fully_paid).length;
                    frappe.show_alert({ message: __("Payment Entry {0} created", [m.name]), indicator: "green" });
                    self.$status_bar.html(`<span class="fe-status-ok"><i class="fa fa-check"></i> <a href="/app/payment-entry/${m.name}" target="_blank">${m.name}</a> | ${fully_paid} fully paid, ${partial} partial</span>`);
                    self.load_pending();
                    self.$amount.val("");
                    self.preview_allocation();
                } else {
                    self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Payment Entry not created</span>');
                }
            },
            error: function() {
                self.$root.find("#fpe-create").prop("disabled", false);
                self.$status_bar.html('<span class="fe-status-error"><i class="fa fa-times"></i> Failed to create payment entry</span>');
            }
        });
    }
};