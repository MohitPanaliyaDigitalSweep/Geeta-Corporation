frappe.provide("fast_entry_app");

frappe.pages["fast-partygroup-report"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Party Group Details"), single_column: true });
    frappe.breadcrumbs.add({
        type: "Custom",
        label: __("Party Group Report"),
        route: "fast-partygroup-report",
    });
    new fast_entry_app.PartyGroupReport({ container: wrapper });
};

fast_entry_app.PartyGroupReport = class PartyGroupReport {
    constructor({ container }) {
        this.$container = $(container);
        this.data = [];
        this.group_summary = [];
        this.product_summary = [];
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
                            <span id="pgr-filter-tag" class="frms-filter-tag"></span>
                            <button class="btn-export" id="pgr-export"><i class="fa fa-download"></i> Export CSV</button>
                        </div>
                    </div>
                    <div class="frms-filter-row">
                        <div class="frms-filter-group"><label>Period</label><div id="pgr-period"></div></div>
                        <div class="frms-filter-group"><label>Compare</label><div id="pgr-compare"></div></div>
                        <div class="frms-filter-sep"></div>
                        <div class="frms-filter-group"><label>Company</label><div id="pgr-company"></div></div>
                        <div class="frms-filter-group"><label>Party Group</label><div id="pgr-group"></div></div>
                        <div class="frms-filter-group"><label>Item</label><div id="pgr-item"></div></div>
                    </div>
                </div>
            </div>
            <div id="pgr-period-info" style="font-size:12px;color:#666;margin-bottom:10px;"></div>
            <div id="pgr-kpi-area" class="frms-anim" style="animation-delay:0.08s;"></div>
            <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:14px;">
                <div class="frms-chart-card frms-anim" style="margin-bottom:0;animation-delay:0.12s;">
                    <div class="frms-chart-head">
                        <div class="frms-chart-icon" style="background:#dbeafe;color:#3b82f6;"><i class="fa fa-users"></i></div>
                        <div><div class="frms-chart-title">Sales by Party Group</div></div>
                    </div>
                    <div id="chart-pg-amount"></div>
                </div>
                <div class="frms-chart-card frms-anim" style="margin-bottom:0;animation-delay:0.14s;">
                    <div class="frms-chart-head">
                        <div class="frms-chart-icon" style="background:#ede9fe;color:#7c3aed;"><i class="fa fa-cube"></i></div>
                        <div><div class="frms-chart-title">Top Products</div></div>
                    </div>
                    <div id="chart-item-amount"></div>
                </div>
                <div class="frms-chart-card frms-anim" style="margin-bottom:0;animation-delay:0.16s;">
                    <div class="frms-chart-head">
                        <div class="frms-chart-icon" style="background:#d1fae5;color:#059669;"><i class="fa fa-user-plus"></i></div>
                        <div><div class="frms-chart-title">Customers by Group</div></div>
                    </div>
                    <div id="chart-pg-customers"></div>
                </div>
            </div>
            <div id="pgr-group-area" class="frms-anim" style="animation-delay:0.16s;"></div>
            <div id="pgr-product-area" class="frms-anim" style="animation-delay:0.20s;"></div>
            <div id="pgr-detail-area" class="frms-anim" style="animation-delay:0.24s;"></div>
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
                self.party_groups = (d.party_groups || []).map(g => ({ value: g, label: g }));
                self.items = (d.items || []).map(i => ({ value: i, label: i }));

                const onFilterChange = () => { self.updateFilterTag(); self._debounce_search(); };

                self.periodChips = new fast_entry_app.report_ui.PeriodChips({
                    container: "#pgr-period",
                    periods: [
                        { value: "custom", label: "Custom" },
                        { value: "month", label: "MTD" },
                        { value: "quarter", label: "QTD" },
                        { value: "year", label: "YTD" },
                    ],
                    onChange: (v) => { self.onPeriodChange(v); self._debounce_search(); },
                });

                self.compareDropdown = new fast_entry_app.report_ui.CompareDropdown({
                    container: "#pgr-compare",
                    options: [
                        { value: "month", label: "vs Last Month" },
                        { value: "quarter", label: "vs Last Quarter" },
                        { value: "year", label: "vs Last Year" },
                    ],
                    onChange: () => self._debounce_search(),
                });

                self.companyMS = new fast_entry_app.report_ui.MultiSelect({
                    container: "#pgr-company", options: self.companies, onChange: onFilterChange,
                });
                self.groupMS = new fast_entry_app.report_ui.MultiSelect({
                    container: "#pgr-group", options: self.party_groups, onChange: onFilterChange,
                });
                self.itemMS = new fast_entry_app.report_ui.MultiSelect({
                    container: "#pgr-item", options: self.items, onChange: onFilterChange,
                });

                self.set_default_dates();
                self.$container.find("#pgr-export").on("click", () => self.export_csv());
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
        const pg = this.groupMS.getSelected();
        if (co.length < this.companies.length && co.length > 0) tags.push(co.length + " companies");
        if (pg.length < this.party_groups.length && pg.length > 0) tags.push(pg.length + " party groups");
        this.$container.find("#pgr-filter-tag").text(tags.join(" | ") || "All");
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
            party_groups: this.groupMS.getSelected(),
            companies: this.companyMS.getSelected(),
            items: this.itemMS.getSelected(),
        };

        frappe.call({
            method: "fast_entry_app.api.reports.get_partygroup_report",
            args: { filters },
            callback: function(r) {
                if (!r.message) return;
                self.data = r.message.data || [];
                self.group_summary = r.message.group_summary || [];
                self.product_summary = r.message.product_summary || [];
                self.charts = r.message.charts || {};
                self.period_info = r.message;
                self.render_report();
            },
        });
    }

    render_report() {
        const pi = this.period_info;
        this.$container.find("#pgr-period-info").html(
            `<b>Current:</b> ${pi.current_period.from_date} to ${pi.current_period.to_date} &nbsp;|&nbsp; <b>Previous:</b> ${pi.previous_period.from_date} to ${pi.previous_period.to_date}`
        );
        this.render_kpis();
        this.render_charts();
        this.render_group_summary();
        this.render_product_summary();
        this.render_detail();
    }

    render_kpis() {
        const k = this.charts.kpis;
        if (!k) return;
        fast_entry_app.report_ui.render_kpis(this.$container.find("#pgr-kpi-area"), [
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
        if (c.group_amount && c.group_amount.labels.length) {
            fast_entry_app.report_ui.render_bar("#chart-pg-amount", c.group_amount.labels, c.group_amount.values, { currency: true });
        }
        if (c.item_amount && c.item_amount.labels.length) {
            fast_entry_app.report_ui.render_bar("#chart-item-amount", c.item_amount.labels, c.item_amount.values, { currency: true });
        }
        if (c.group_customers && c.group_customers.labels.length) {
            fast_entry_app.report_ui.render_bar("#chart-pg-customers", c.group_customers.labels, c.group_customers.values);
        }
    }

    render_group_summary() {
        const headers = [
            { key: "party_group", label: "Party Group" },
            { key: "customer_count", label: "Customers", align: "right" },
            { key: "item_count", label: "Items", align: "right" },
            { key: "cur_amount", label: "Current Amount", align: "right" },
            { key: "prev_amount", label: "Previous Amount", align: "right" },
            { key: "diff_amount", label: "Difference", align: "right" },
            { key: "pct_amount", label: "% Change", align: "right" },
            { key: "cur_outstanding", label: "Outstanding", align: "right" },
            { key: "cur_pcs", label: "Current PCS", align: "right" },
            { key: "cur_box", label: "Current Box", align: "right" },
            { key: "cur_ltr", label: "Current Ltr", align: "right" },
        ];
        const rows = this.group_summary.map(r => ({
            ...r,
            cur_amount: "\u20b9" + (r.cur_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            prev_amount: "\u20b9" + (r.prev_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            diff_amount: "\u20b9" + (r.diff_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            pct_amount: (r.pct_amount || 0).toFixed(1) + "%",
            cur_outstanding: (r.cur_outstanding || 0) > 0 ? '<span style="color:#dc2626;font-weight:700;">\u20b9' + (r.cur_outstanding || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }) + "</span>" : "\u20b90.00",
            cur_pcs: (r.cur_pcs || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_box: (r.cur_box || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_ltr: (r.cur_ltr || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
        }));
        this.$container.find("#pgr-group-area").html('<div class="frms-chart-card"><div class="frms-chart-head"><div class="frms-chart-icon" style="background:#dbeafe;color:#3b82f6;"><i class="fa fa-users"></i></div><div><div class="frms-chart-title">Party Group Summary</div></div></div><div id="pgr-group-table"></div></div>');
        fast_entry_app.report_ui.render_table("#pgr-group-table", headers, rows);
    }

    render_product_summary() {
        const headers = [
            { key: "item_name", label: "Product" },
            { key: "group_count", label: "Groups", align: "right" },
            { key: "cur_amount", label: "Current Amount", align: "right" },
            { key: "prev_amount", label: "Previous Amount", align: "right" },
            { key: "diff_amount", label: "Difference", align: "right" },
            { key: "pct_amount", label: "% Change", align: "right" },
            { key: "cur_pcs", label: "Current PCS", align: "right" },
            { key: "cur_box", label: "Current Box", align: "right" },
            { key: "cur_ltr", label: "Current Ltr", align: "right" },
        ];
        const rows = this.product_summary.map(r => ({
            ...r,
            cur_amount: "\u20b9" + (r.cur_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            prev_amount: "\u20b9" + (r.prev_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            diff_amount: "\u20b9" + (r.diff_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            pct_amount: (r.pct_amount || 0).toFixed(1) + "%",
            cur_pcs: (r.cur_pcs || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_box: (r.cur_box || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_ltr: (r.cur_ltr || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
        }));
        this.$container.find("#pgr-product-area").html('<div class="frms-chart-card"><div class="frms-chart-head"><div class="frms-chart-icon" style="background:#ede9fe;color:#7c3aed;"><i class="fa fa-cube"></i></div><div><div class="frms-chart-title">Product Summary</div></div></div><div id="pgr-item-table"></div></div>');
        fast_entry_app.report_ui.render_table("#pgr-item-table", headers, rows);
    }

    render_detail() {
        const headers = [
            { key: "party_group", label: "Party Group" },
            { key: "customer", label: "Customer" },
            { key: "item_name", label: "Item" },
            { key: "cur_amount", label: "Amount", align: "right" },
            { key: "prev_amount", label: "Prev Amount", align: "right" },
            { key: "diff_amount", label: "Diff", align: "right" },
            { key: "pct_amount", label: "%", align: "right" },
            { key: "cur_pcs", label: "PCS", align: "right" },
            { key: "cur_box", label: "Box", align: "right" },
            { key: "cur_ltr", label: "Ltr", align: "right" },
            { key: "cur_invoices", label: "Invoices", align: "right" },
        ];
        const rows = this.data.map(r => ({
            ...r,
            cur_amount: "\u20b9" + (r.cur_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            prev_amount: "\u20b9" + (r.prev_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            diff_amount: "\u20b9" + (r.diff_amount || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            pct_amount: (r.pct_amount || 0).toFixed(1) + "%",
            cur_pcs: (r.cur_pcs || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_box: (r.cur_box || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
            cur_ltr: (r.cur_ltr || 0).toLocaleString("en-IN", { minimumFractionDigits: 2 }),
        }));
        this.$container.find("#pgr-detail-area").html('<div class="frms-chart-card"><div class="frms-chart-head"><div class="frms-chart-icon" style="background:#fef3c7;color:#d97706;"><i class="fa fa-list"></i></div><div><div class="frms-chart-title">Detailed Breakdown</div><div class="frms-chart-sub">Party Group \u2192 Customer \u2192 Item</div></div></div><div id="pgr-detail-table"></div></div>');
        fast_entry_app.report_ui.render_table("#pgr-detail-table", headers, rows);
    }

    export_csv() {
        const headers = [
            { key: "party_group", label: "Party Group" },
            { key: "customer", label: "Customer" },
            { key: "item_name", label: "Item" },
            { key: "cur_amount", label: "Current Amount" },
            { key: "prev_amount", label: "Previous Amount" },
            { key: "diff_amount", label: "Difference" },
            { key: "pct_amount", label: "% Change" },
            { key: "cur_pcs", label: "Current PCS" },
            { key: "cur_box", label: "Current Box" },
            { key: "cur_ltr", label: "Current Ltr" },
            { key: "cur_invoices", label: "Invoices" },
        ];
        fast_entry_app.report_ui.export_csv(headers, this.data, "partygroup_report");
    }
};
