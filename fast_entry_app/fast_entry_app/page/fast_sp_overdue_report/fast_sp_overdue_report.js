frappe.provide("fast_entry_app");

frappe.pages["fast-sp-overdue-report"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Sales Person Sales & Overdue"), single_column: true });
    frappe.breadcrumbs.add({
        type: "Custom",
        label: __("SP Overdue Report"),
        route: "fast-sp-overdue-report",
    });
    new fast_entry_app.SPOverdueReport({ container: wrapper });
};

fast_entry_app.SPOverdueReport = class SPOverdueReport {
    constructor({ container }) {
        this.$container = $(container);
        this.data = [];
        this.summary = [];
        this.charts = {};
        this.render();
        this.load_filters();
    }

    render() {
        this.$container.html(`
        <div class="frms-page" style="padding:0 12px 12px;">
            <div class="frms-sticky-top frms-anim">
                <div class="frms-filter-bar">
                    <div class="frms-filter-header">
                        <div class="frms-filter-header-title"><i class="fa fa-filter"></i> Filters</div>
                        <div class="frms-filter-actions">
                            <span id="sor-filter-tag" class="frms-filter-tag"></span>
                            <button class="btn-export" id="sor-export"><i class="fa fa-download"></i> Export CSV</button>
                        </div>
                    </div>
                    <div class="frms-filter-row">
                        <div class="frms-filter-group"><label>Period</label><div id="sor-period"></div></div>
                        <div class="frms-filter-group"><label>Compare</label><div id="sor-compare"></div></div>
                        <div class="frms-filter-sep"></div>
                        <div class="frms-filter-group"><label>Company</label><div id="sor-company"></div></div>
                        <div class="frms-filter-group"><label>Sales Person</label><div id="sor-sp"></div></div>
                        <div class="frms-filter-group"><label>Item</label><div id="sor-item"></div></div>
                    </div>
                </div>
            </div>
            <div id="sor-period-info" style="font-size:12px;color:#666;margin-bottom:10px;"></div>
            <div id="sor-kpi-area" class="frms-anim" style="animation-delay:0.08s;"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
                <div class="frms-chart-card frms-anim" style="margin-bottom:0;animation-delay:0.12s;">
                    <div class="frms-chart-head">
                        <div class="frms-chart-icon" style="background:#fee2e2;color:#dc2626;"><i class="fa fa-exclamation-triangle"></i></div>
                        <div><div class="frms-chart-title">Outstanding by Sales Person</div></div>
                    </div>
                    <div id="chart-sp-outstanding"></div>
                </div>
                <div class="frms-chart-card frms-anim" style="margin-bottom:0;animation-delay:0.14s;">
                    <div class="frms-chart-head">
                        <div class="frms-chart-icon" style="background:#dbeafe;color:#3b82f6;"><i class="fa fa-rupee"></i></div>
                        <div><div class="frms-chart-title">Sales by Sales Person</div></div>
                    </div>
                    <div id="chart-sp-amount"></div>
                </div>
            </div>
            <div id="sor-summary-area" class="frms-anim" style="animation-delay:0.16s;"></div>
            <div id="sor-detail-area" class="frms-anim" style="animation-delay:0.20s;"></div>
        </div>`);
    }

    load_filters() {
        const self = this;
        frappe.call({
            method: "fast_entry_app.api.reports.get_filter_options",
            callback: function(r) {
                if (!r.message) return;
                const d = r.message;
                self.companies = (d.companies || []).map(c => ({ value: c, label: c }));
                self.sales_persons = (d.sales_persons || []).map(s => ({ value: s, label: s }));
                self.items = (d.items || []).map(i => ({ value: i, label: i }));

                const onFilterChange = () => { self.updateFilterTag(); self._debounce_search(); };

                self.periodChips = new fast_entry_app.report_ui.PeriodChips({
                    container: "#sor-period",
                    periods: [
                        { value: "custom", label: "Custom" },
                        { value: "month", label: "MTD" },
                        { value: "quarter", label: "QTD" },
                        { value: "year", label: "YTD" },
                    ],
                    onChange: (v) => { self.onPeriodChange(v); self._debounce_search(); },
                });

                self.compareDropdown = new fast_entry_app.report_ui.CompareDropdown({
                    container: "#sor-compare",
                    options: [
                        { value: "month", label: "vs Last Month" },
                        { value: "quarter", label: "vs Last Quarter" },
                        { value: "year", label: "vs Last Year" },
                    ],
                    onChange: () => self._debounce_search(),
                });

                self.companyMS = new fast_entry_app.report_ui.MultiSelect({
                    container: "#sor-company", options: self.companies, onChange: onFilterChange,
                });
                self.spMS = new fast_entry_app.report_ui.MultiSelect({
                    container: "#sor-sp", options: self.sales_persons, onChange: onFilterChange,
                });
                self.itemMS = new fast_entry_app.report_ui.MultiSelect({
                    container: "#sor-item", options: self.items, onChange: onFilterChange,
                });

                self.set_default_dates();
                self.$container.find("#sor-export").on("click", () => self.export_csv());
                self._debounce_search = frappe.utils.debounce(() => self.search(), 500);
                self.search();
            },
        });
    }

    set_default_dates() {
        const today = new Date();
        const first = new Date(today.getFullYear(), today.getMonth(), 1);
        this.from_date = this.fmt(first);
        this.to_date = this.fmt(today);
    }

    fmt(d) { return d.toISOString().split("T")[0]; }

    onPeriodChange(period) {
        const today = new Date();
        if (period === "month") {
            this.from_date = this.fmt(new Date(today.getFullYear(), today.getMonth(), 1));
            this.to_date = this.fmt(today);
        } else if (period === "quarter") {
            const qm = Math.floor(today.getMonth() / 3) * 3;
            this.from_date = this.fmt(new Date(today.getFullYear(), qm, 1));
            this.to_date = this.fmt(today);
        } else if (period === "year") {
            this.from_date = this.fmt(new Date(today.getFullYear(), 0, 1));
            this.to_date = this.fmt(today);
        }
    }

    updateFilterTag() {
        const tags = [];
        const co = this.companyMS.getSelected();
        const sp = this.spMS.getSelected();
        if (co.length < this.companies.length && co.length > 0) tags.push(co.length + " companies");
        if (sp.length < this.sales_persons.length && sp.length > 0) tags.push(sp.length + " sales persons");
        this.$container.find("#sor-filter-tag").text(tags.join(" | ") || "All");
    }

    search() {
        const self = this;
        const period = this.periodChips.getActive();
        const compare = this.compareDropdown.getValue();
        let from = this.from_date, to = this.to_date;
        if (compare === "month") { const d = new Date(from); d.setMonth(d.getMonth() - 1); from = this.fmt(d); }
        else if (compare === "quarter") { const d = new Date(from); d.setMonth(d.getMonth() - 3); from = this.fmt(d); }
        else if (compare === "year") { const d = new Date(from); d.setFullYear(d.getFullYear() - 1); from = this.fmt(d); }

        const filters = {
            from_date: from, to_date: to, period: period,
            sales_persons: this.spMS.getSelected(),
            companies: this.companyMS.getSelected(),
            items: this.itemMS.getSelected(),
        };

        frappe.call({
            method: "fast_entry_app.api.reports.get_sp_overdue_report",
            args: { filters },
            callback: function(r) {
                if (!r.message) return;
                self.data = r.message.data || [];
                self.summary = r.message.summary || [];
                self.charts = r.message.charts || {};
                self.period_info = r.message;
                self.render_report();
            },
        });
    }

    render_report() {
        const pi = this.period_info;
        this.$container.find("#sor-period-info").html(
            `<b>Current:</b> ${pi.current_period.from_date} to ${pi.current_period.to_date} &nbsp;|&nbsp; <b>Previous:</b> ${pi.previous_period.from_date} to ${pi.previous_period.to_date}`
        );
        this.render_kpis();
        this.render_charts();
        this.render_summary();
        this.render_detail();
    }

    render_kpis() {
        const k = this.charts.kpis;
        if (!k) return;
        fast_entry_app.report_ui.render_kpis(this.$container.find("#sor-kpi-area"), [
            { label: "Total Sales", cur_value: k.total_amount.cur, prev_value: k.total_amount.prev, icon: "fa-rupee" },
            { label: "Invoices", cur_value: k.total_invoices.cur, prev_value: k.total_invoices.prev, icon: "fa-file-text-o" },
            { label: "Avg Order", cur_value: k.avg_order.cur, prev_value: k.avg_order.prev, icon: "fa-calculator" },
            { label: "Total PCS", cur_value: k.total_pcs.cur, prev_value: k.total_pcs.prev, icon: "fa-cubes" },
            { label: "Total Box", cur_value: k.total_box.cur, prev_value: k.total_box.prev, icon: "fa-archive" },
            { label: "Total Ltr", cur_value: k.total_ltr.cur, prev_value: k.total_ltr.prev, icon: "fa-tint" },
        ]);
    }

    render_charts() {
        const c = this.charts;
        if (c.sp_outstanding && c.sp_outstanding.labels.length) {
            fast_entry_app.report_ui.render_bar("#chart-sp-outstanding", c.sp_outstanding.labels, c.sp_outstanding.values, { currency: true });
        }
        if (c.sp_amount && c.sp_amount.labels.length) {
            fast_entry_app.report_ui.render_bar("#chart-sp-amount", c.sp_amount.labels, c.sp_amount.values, { currency: true });
        }
    }

    render_summary() {
        const headers = [
            { key: "sales_person", label: "Sales Person" },
            { key: "customer_count", label: "Customers", align: "right" },
            { key: "overdue_count", label: "Overdue Invoices", align: "right" },
            { key: "cur_amount", label: "Current Sales", align: "right" },
            { key: "prev_amount", label: "Previous Sales", align: "right" },
            { key: "cur_outstanding", label: "Outstanding", align: "right" },
            { key: "cur_pcs", label: "Current PCS", align: "right" },
            { key: "cur_box", label: "Current Box", align: "right" },
            { key: "cur_ltr", label: "Current Ltr", align: "right" },
        ];
        const rows = this.summary.map(r => ({
            ...r,
            cur_amount: "\u20b9" + (r.cur_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            prev_amount: "\u20b9" + (r.prev_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_outstanding: '<span style="color:#dc2626;font-weight:700;">\u20b9' + (r.cur_outstanding || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }) + "</span>",
            cur_pcs: (r.cur_pcs || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_box: (r.cur_box || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_ltr: (r.cur_ltr || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
        }));
        this.$container.find("#sor-summary-area").html('<div class="frms-chart-card"><div class="frms-chart-head"><div class="frms-chart-icon" style="background:#fee2e2;color:#dc2626;"><i class="fa fa-exclamation-circle"></i></div><div><div class="frms-chart-title">Sales Person Summary with Outstanding</div></div></div><div id="sor-summary-table"></div></div>');
        fast_entry_app.report_ui.render_table("#sor-summary-table", headers, rows);
    }

    render_detail() {
        const headers = [
            { key: "sales_person", label: "Sales Person" },
            { key: "customer", label: "Customer" },
            { key: "invoice_no", label: "Invoice" },
            { key: "posting_date", label: "Date", align: "right" },
            { key: "due_date", label: "Due Date", align: "right" },
            { key: "days_overdue", label: "Days Overdue", align: "right" },
            { key: "item_list", label: "Items" },
            { key: "cur_amount", label: "Amount", align: "right" },
            { key: "cur_outstanding", label: "Outstanding", align: "right" },
            { key: "cur_pcs", label: "PCS", align: "right" },
            { key: "cur_box", label: "Box", align: "right" },
            { key: "cur_ltr", label: "Ltr", align: "right" },
        ];
        const rows = this.data.map(r => ({
            ...r,
            cur_amount: "\u20b9" + (r.cur_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_outstanding: r.cur_outstanding > 0 ? '<span style="color:#dc2626;font-weight:700;">\u20b9' + (r.cur_outstanding || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }) + "</span>" : "\u20b90.00",
            days_overdue: r.days_overdue > 0 ? '<span class="frms-badge frms-badge-danger">' + r.days_overdue + " days</span>" : "-",
            cur_pcs: (r.cur_pcs || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_box: (r.cur_box || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_ltr: (r.cur_ltr || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
        }));
        this.$container.find("#sor-detail-area").html('<div class="frms-chart-card"><div class="frms-chart-head"><div class="frms-chart-icon" style="background:#fef3c7;color:#d97706;"><i class="fa fa-list"></i></div><div><div class="frms-chart-title">Invoice Details</div><div class="frms-chart-sub">Sorted by days overdue (highest first)</div></div></div><div id="sor-detail-table"></div></div>');
        fast_entry_app.report_ui.render_table("#sor-detail-table", headers, rows);
    }

    export_csv() {
        const headers = [
            { key: "sales_person", label: "Sales Person" },
            { key: "customer", label: "Customer" },
            { key: "invoice_no", label: "Invoice" },
            { key: "posting_date", label: "Date" },
            { key: "due_date", label: "Due Date" },
            { key: "days_overdue", label: "Days Overdue" },
            { key: "cur_amount", label: "Amount" },
            { key: "cur_outstanding", label: "Outstanding" },
            { key: "cur_pcs", label: "PCS" },
            { key: "cur_box", label: "Box" },
            { key: "cur_ltr", label: "Ltr" },
            { key: "item_list", label: "Items" },
        ];
        fast_entry_app.report_ui.export_csv(headers, this.data, "sp_overdue_report");
    }
};
