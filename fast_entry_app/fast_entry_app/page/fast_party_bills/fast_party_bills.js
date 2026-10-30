frappe.provide("fast_entry_app");

frappe.pages["fast-party-bills"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Party Bills"), single_column: true });
    fast_entry_app.party_bills_page = new fast_entry_app.PartyBills(wrapper);
};

fast_entry_app.PartyBills = class PartyBills {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.build();
    }

    flt(v) { return parseFloat(v) || 0; }
    fmt(v) { return (this.flt(v)).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
    esc(v) { return frappe.utils.escape_html(v == null ? "" : String(v)); }

    build() {
        this.$root = $(this.wrapper.page.main);
        this.$root.html(this.get_html());
        this.bind_elements();
        this.load_companies();
    }

    get_html() {
        return `<div class="fast-entry-container" style="max-width:900px;margin:0 auto;">
            <div class="fe-header-section">
                <div class="fe-header-row">
                    <div class="fe-field"><label>Company <span class="reqd">*</span></label><select class="fe-input" id="fpb-company"></select></div>
                    <div class="fe-field"><label>Party Type</label>
                        <select class="fe-input" id="fpb-party-type">
                            <option value="Customer">Customer (Receivable)</option>
                            <option value="Supplier">Supplier (Payable)</option>
                        </select>
                    </div>
                    <div class="fe-field fe-field-wide"><label>Search Party</label><input type="text" class="fe-input" id="fpb-search" placeholder="Search..." /></div>
                    <div class="fe-field" style="flex:0 0 120px;align-self:flex-end;"><button class="fe-btn fe-btn-primary" id="fpb-load" style="width:100%;justify-content:center;"><i class="fa fa-search"></i> Load</button></div>
                </div>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:10px;margin-bottom:12px;">
                <div class="fe-card" style="padding:12px;"><div style="font-size:11px;color:#6b7280;">Total Outstanding</div><div style="font-size:18px;font-weight:700;color:#111827;" id="fpb-total-outstanding">0.00</div></div>
                <div class="fe-card" style="padding:12px;"><div style="font-size:11px;color:#6b7280;">Total Overdue</div><div style="font-size:18px;font-weight:700;color:#dc2626;" id="fpb-total-overdue">0.00</div></div>
                <div class="fe-card" style="padding:12px;"><div style="font-size:11px;color:#6b7280;">Overdue Invoices</div><div style="font-size:18px;font-weight:700;color:#f59e0b;" id="fpb-overdue-count">0</div></div>
                <div class="fe-card" style="padding:12px;"><div style="font-size:11px;color:#6b7280;">Total Invoices</div><div style="font-size:18px;font-weight:700;color:#111827;" id="fpb-total-invoices">0</div></div>
            </div>
            <div id="fpb-party-list"></div>
            <div class="fe-status-bar" id="fpb-status-bar"></div>
        </div>`;
    }

    bind_elements() {
        const self = this;
        this.$company = this.$root.find("#fpb-company");
        this.$party_type = this.$root.find("#fpb-party-type");
        this.$search = this.$root.find("#fpb-search");
        this.$root.find("#fpb-load").on("click", () => this.load_data());
        this.$company.on("change", () => localStorage.setItem("fpb_company", this.$company.val()));
        this.$party_type.on("change", () => this.load_data());
        this.$search.on("input", () => { clearTimeout(this._st); this._st = setTimeout(() => this.load_data(), 400); });
    }

    load_companies() {
        const self = this;
        frappe.call({ method: "frappe.client.get_list", args: { doctype: "Company", filters: {}, fields: ["name"], limit_page_length: 100 },
            callback: function(r) {
                const companies = r.message || [];
                self.$company.empty().append('<option value="">Select Company</option>');
                companies.forEach(c => self.$company.append(`<option value="${c.name}">${c.name}</option>`));
                const ls = localStorage.getItem("fpb_company");
                if (ls && companies.find(c => c.name === ls)) self.$company.val(ls);
                else if (companies.length === 1) self.$company.val(companies[0].name);
            }
        });
    }

    load_data() {
        const self = this;
        const company = this.$company.val();
        const party_type = this.$party_type.val();
        const search = this.$search.val();
        if (!company) { frappe.msgprint({ title: "Missing", indicator: "orange", message: "Select company first." }); return; }
        this.$root.find("#fpb-party-list").html('<div style="text-align:center;padding:20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin"></i> Loading...</div>');
        frappe.call({
            method: "fast_entry_app.api.party_bills.get_party_bills_summary",
            args: { company: company, party_type: party_type, search: search || "" },
            callback: function(r) {
                const parties = r.message || [];
                let html = "";
                if (!parties.length) {
                    html = '<div style="text-align:center;padding:20px;color:#9ca3af;">No pending bills found.</div>';
                } else {
                    parties.forEach(function(p) {
                        html += `<div style="background:#fff;border-radius:8px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,0.08);overflow:hidden;">
                            <div style="display:flex;align-items:center;justify-content:space-between;padding:12px 16px;cursor:pointer;" onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'block':'none'">
                                <div>
                                    <div style="font-weight:600;font-size:13px;color:#111827;">${self.esc(p.party_name || p.party)}</div>
                                    <div style="font-size:11px;color:#6b7280;">${p.invoice_count} invoice${p.invoice_count === 1 ? "" : "s"}</div>
                                </div>
                                <div style="text-align:right;">
                                    <div style="font-weight:700;font-size:13px;color:${p.overdue_amount > 0 ? '#dc2626' : '#111827'};">Rs. ${self.fmt(p.total_outstanding)}</div>
                                    ${p.overdue_amount > 0 ? `<div style="font-size:11px;color:#dc2626;">Overdue: Rs. ${self.fmt(p.overdue_amount)}</div>` : ""}
                                </div>
                            </div>
                            <div style="display:none;padding:0 16px 12px;">
                                ${(p.invoices || []).map(function(inv) {
                                    return `<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #f3f4f6;font-size:12px;">
                                        <div><div style="font-weight:500;">${self.esc(inv.name)}</div><div style="color:#6b7280;font-size:11px;">${inv.posting_date}${inv.due_date ? " · Due " + inv.due_date : ""}</div></div>
                                        <div style="text-align:right;"><div style="font-weight:600;color:${inv.is_overdue ? '#dc2626' : '#374151'};">Rs. ${self.fmt(inv.outstanding_amount)}</div>${inv.is_overdue ? '<div style="font-size:10px;color:#dc2626;font-weight:600;">Overdue</div>' : ''}</div>
                                    </div>`;
                                }).join("")}
                            </div>
                        </div>`;
                    });
                }
                self.$root.find("#fpb-party-list").html(html);
            }
        });
        frappe.call({
            method: "fast_entry_app.api.party_bills.get_party_overdue_summary",
            args: { company: company, party_type: party_type },
            callback: function(r) {
                const s = r.message || {};
                self.$root.find("#fpb-total-outstanding").text(self.fmt(s.total_outstanding));
                self.$root.find("#fpb-total-overdue").text(self.fmt(s.total_overdue));
                self.$root.find("#fpb-overdue-count").text(s.overdue_count || 0);
                self.$root.find("#fpb-total-invoices").text(s.total_invoices || 0);
            }
        });
    }
};