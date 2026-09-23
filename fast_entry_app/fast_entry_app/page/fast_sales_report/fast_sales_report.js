frappe.provide("fast_entry_app");

frappe.pages["fast-sales-report"].on_page_load = function(wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Sales Person Performance"), single_column: true });
    new fast_entry_app.FastSalesReport({ container: wrapper });
};

fast_entry_app.FastSalesReport = class FastSalesReport {
    constructor({ container }) {
        this.$container = $(container);
        this.data = [];
        this.summary = [];
        this.pincode_summary = [];
        this.sp_pincode_summary = [];
        this.charts = {};
        this.charts_rendered = {};
        this.render();
        this.load_filters();
    }

    render() {
        this.$container.html(`
        <div class="fe-report-page" style="padding:0 12px 12px;">
            <div class="fe-report-header" style="padding:12px 0 0;">
                <h2 style="margin:0;font-size:18px;">Sales Person Performance Report</h2>
            </div>
            <div class="fe-report-filters" style="border:1px solid #d1d8dd;border-radius:6px;padding:10px 12px;margin:10px 0 12px;background:#fafbfc;">
                <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px 12px;">
                    <div class="fe-field">
                        <label style="font-size:10px;font-weight:600;color:#666;text-transform:uppercase;">Period</label>
                        <select id="sr-period" class="form-control form-control-sm input-sm" style="font-size:12px;">
                            <option value="custom">Custom</option>
                            <option value="month">Month vs Last Month</option>
                            <option value="quarter">Quarter vs Last Quarter</option>
                            <option value="year">Year vs Last Year</option>
                        </select>
                    </div>
                    <div class="fe-field">
                        <label style="font-size:10px;font-weight:600;color:#666;text-transform:uppercase;">From Date</label>
                        <input type="date" id="sr-from" class="form-control form-control-sm input-sm" style="font-size:12px;" />
                    </div>
                    <div class="fe-field">
                        <label style="font-size:10px;font-weight:600;color:#666;text-transform:uppercase;">To Date</label>
                        <input type="date" id="sr-to" class="form-control form-control-sm input-sm" style="font-size:12px;" />
                    </div>
                    <div class="fe-field">
                        <label style="font-size:10px;font-weight:600;color:#666;text-transform:uppercase;">Sales Person</label>
                        <select id="sr-sp" class="form-control form-control-sm input-sm" style="font-size:12px;"><option value="">All</option></select>
                    </div>
                    <div class="fe-field">
                        <label style="font-size:10px;font-weight:600;color:#666;text-transform:uppercase;">Company</label>
                        <select id="sr-company" class="form-control form-control-sm input-sm" style="font-size:12px;"><option value="">All</option></select>
                    </div>
                    <div class="fe-field">
                        <label style="font-size:10px;font-weight:600;color:#666;text-transform:uppercase;">Customer</label>
                        <select id="sr-customer" class="form-control form-control-sm input-sm" style="font-size:12px;"><option value="">All</option></select>
                    </div>
                    <div class="fe-field">
                        <label style="font-size:10px;font-weight:600;color:#666;text-transform:uppercase;">Party Group</label>
                        <select id="sr-group" class="form-control form-control-sm input-sm" style="font-size:12px;"><option value="">All</option></select>
                    </div>
                    <div class="fe-field">
                        <label style="font-size:10px;font-weight:600;color:#666;text-transform:uppercase;">Pincode</label>
                        <select id="sr-pincode" class="form-control form-control-sm input-sm" style="font-size:12px;"><option value="">All</option></select>
                    </div>
                    <div class="fe-field">
                        <label style="font-size:10px;font-weight:600;color:#666;text-transform:uppercase;">Item</label>
                        <select id="sr-item" class="form-control form-control-sm input-sm" style="font-size:12px;"><option value="">All</option></select>
                    </div>
                    <div class="fe-field" style="display:flex;gap:6px;align-items:flex-end;padding-bottom:1px;">
                        <button class="btn btn-sm btn-primary" id="sr-search" style="height:30px;font-size:12px;"><i class="fa fa-search"></i> Search</button>
                        <button class="btn btn-sm btn-default" id="sr-export" style="height:30px;font-size:12px;"><i class="fa fa-download"></i> Export</button>
                    </div>
                </div>
            </div>
            <div id="sr-period-info" style="font-size:12px;color:#666;margin-bottom:10px;"></div>
            <div id="sr-kpi-area"></div>
            <div id="sr-charts-area" style="margin-bottom:12px;"></div>
            <div id="sr-summary-area"></div>
            <div id="sr-pincode-area"></div>
            <div id="sr-sp-pincode-area"></div>
            <div id="sr-detail-area" style="overflow-x:auto;"></div>
        </div>`);

        this.$period = this.$container.find("#sr-period");
        this.$from = this.$container.find("#sr-from");
        this.$to = this.$container.find("#sr-to");
        this.$sp = this.$container.find("#sr-sp");
        this.$company = this.$container.find("#sr-company");
        this.$customer = this.$container.find("#sr-customer");
        this.$group = this.$container.find("#sr-group");
        this.$pincode = this.$container.find("#sr-pincode");
        this.$item = this.$container.find("#sr-item");
        this.$kpi = this.$container.find("#sr-kpi-area");
        this.$charts = this.$container.find("#sr-charts-area");
        this.$summary = this.$container.find("#sr-summary-area");
        this.$pincode_area = this.$container.find("#sr-pincode-area");
        this.$sp_pincode = this.$container.find("#sr-sp-pincode-area");
        this.$detail = this.$container.find("#sr-detail-area");
        this.$period_info = this.$container.find("#sr-period-info");

        this.$period.on("change", () => this.on_period_change());
        this.$container.find("#sr-search").on("click", () => this.search());
        this.$container.find("#sr-export").on("click", () => this.open_export_dialog());

        this.set_default_dates();
    }

    set_default_dates() {
        const today = new Date();
        const first = new Date(today.getFullYear(), today.getMonth(), 1);
        this.$from.val(this.fmt(first));
        this.$to.val(this.fmt(today));
    }

    fmt(d) { return d.toISOString().split("T")[0]; }

    on_period_change() {
        const p = this.$period.val();
        const today = new Date();
        let from, to;
        if (p === "month") { from = new Date(today.getFullYear(), today.getMonth(), 1); to = today; }
        else if (p === "quarter") { const qm = Math.floor(today.getMonth() / 3) * 3; from = new Date(today.getFullYear(), qm, 1); to = today; }
        else if (p === "year") { from = new Date(today.getFullYear(), 0, 1); to = today; }
        if (from) this.$from.val(this.fmt(from));
        if (to) this.$to.val(this.fmt(to));
    }

    load_filters() {
        const self = this;
        frappe.call({
            method: "fast_entry_app.api.sales_person_report.get_filter_options",
            callback: function(r) {
                if (!r.message) return;
                const d = r.message;
                self._fill_select(self.$sp, d.sales_persons);
                self._fill_select(self.$company, d.companies);
                self._fill_select(self.$customer, d.customers);
                self._fill_select(self.$group, d.party_groups);
                self._fill_select(self.$item, d.items);
                self._fill_select(self.$pincode, d.pincodes);
            },
        });
    }

    _fill_select($el, arr) {
        const val = $el.val();
        $el.find("option:gt(0)").remove();
        (arr || []).forEach(v => $el.append(`<option value="${v}">${v}</option>`));
        if (val) $el.val(val);
    }

    get_filters() {
        return {
            from_date: this.$from.val(), to_date: this.$to.val(),
            period: this.$period.val(), sales_person: this.$sp.val(),
            company: this.$company.val(), customer: this.$customer.val(),
            party_group: this.$group.val(), pincode: this.$pincode.val(),
            item_code: this.$item.val(),
        };
    }

    search() {
        const f = this.get_filters();
        if (!f.from_date || !f.to_date) { frappe.msgprint("From/To dates required"); return; }
        const self = this;
        frappe.call({
            method: "fast_entry_app.api.sales_person_report.get_sales_person_performance",
            args: { filters: f },
            callback: function(r) {
                if (!r.message) return;
                self.data = r.message.data || [];
                self.summary = r.message.summary || [];
                self.pincode_summary = r.message.pincode_summary || [];
                self.sp_pincode_summary = r.message.sp_pincode_summary || [];
                self.charts = r.message.charts || {};
                self.period_info = r.message;
                self.charts_rendered = {};
                self.render_report();
            },
        });
    }

    render_report() {
        const pi = this.period_info;
        this.$period_info.html(`<b>Current:</b> ${pi.current_period.from_date} to ${pi.current_period.to_date} &nbsp;|&nbsp; <b>Previous:</b> ${pi.previous_period.from_date} to ${pi.previous_period.to_date}`);
        this.render_kpis();
        this.render_charts();
        this.render_summary();
        this.render_pincode_summary();
        this.render_sp_pincode_summary();
        this.render_detail();
    }

    /* ==================== KPI CARDS ==================== */
    render_kpis() {
        const k = this.charts.kpis || {};
        if (!k.total_amount) { this.$kpi.html(""); return; }

        const pct = (cur, prev) => {
            if (!prev) return cur ? "+100.0%" : "0.0%";
            const d = ((cur - prev) / prev * 100);
            return (d >= 0 ? "+" : "") + d.toFixed(1) + "%";
        };
        const cls = (cur, prev) => cur >= prev ? "color:#27ae60" : "color:#e74c3c";
        const arrow = (cur, prev) => cur >= prev ? "&#9650;" : "&#9660;";
        const fmt = v => (v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

        const cards = [
            { label: "Total Sales", cur: fmt(k.total_amount.cur), prev: fmt(k.total_amount.prev), pct: pct(k.total_amount.cur, k.total_amount.prev), cls: cls(k.total_amount.cur, k.total_amount.prev), icon: "fa-rupee" },
            { label: "Invoices", cur: fmt(k.total_invoices.cur), prev: fmt(k.total_invoices.prev), pct: pct(k.total_invoices.cur, k.total_invoices.prev), cls: cls(k.total_invoices.cur, k.total_invoices.prev), icon: "fa-file-text-o" },
            { label: "Avg Order", cur: fmt(k.avg_order.cur), prev: fmt(k.avg_order.prev), pct: pct(k.avg_order.cur, k.avg_order.prev), cls: cls(k.avg_order.cur, k.avg_order.prev), icon: "fa-calculator" },
            { label: "Total PCS", cur: fmt(k.total_pcs.cur), prev: fmt(k.total_pcs.prev), pct: pct(k.total_pcs.cur, k.total_pcs.prev), cls: cls(k.total_pcs.cur, k.total_pcs.prev), icon: "fa-cubes" },
            { label: "Total Box", cur: fmt(k.total_box.cur), prev: fmt(k.total_box.prev), pct: pct(k.total_box.cur, k.total_box.prev), cls: cls(k.total_box.cur, k.total_box.prev), icon: "fa-archive" },
            { label: "Total Ltr", cur: fmt(k.total_ltr.cur), prev: fmt(k.total_ltr.prev), pct: pct(k.total_ltr.cur, k.total_ltr.prev), cls: cls(k.total_ltr.cur, k.total_ltr.prev), icon: "fa-tint" },
        ];

        let html = `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(170px,1fr));gap:10px;margin-bottom:14px;">`;
        cards.forEach(c => {
            html += `
            <div style="border:1px solid #d1d8dd;border-radius:6px;padding:12px;background:#fff;">
                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                    <i class="fa ${c.icon}" style="font-size:14px;color:#8d99a6;"></i>
                    <span style="font-size:11px;font-weight:600;color:#666;text-transform:uppercase;">${c.label}</span>
                </div>
                <div style="font-size:20px;font-weight:700;color:#1a2138;margin-bottom:2px;">${c.cur}</div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <span style="font-size:11px;color:#8d99a6;">Prev: ${c.prev}</span>
                    <span style="font-size:11px;font-weight:600;${c.cls}">${arrow(k[c.label.toLowerCase().replace(/\s/g,'_')]?.cur, k[c.label.toLowerCase().replace(/\s/g,'_')]?.prev)} ${c.pct}</span>
                </div>
            </div>`;
        });
        html += `</div>`;
        this.$kpi.html(html);
    }

    /* ==================== CHARTS ==================== */
    render_charts() {
        if (!this.charts.kpis) { this.$charts.html(""); return; }

        let html = `
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div style="border:1px solid #d1d8dd;border-radius:6px;padding:12px;background:#fff;">
                <h4 style="margin:0 0 8px;font-size:13px;font-weight:600;color:#1a2138;">Sales by Sales Person</h4>
                <div id="chart-sp-amount" style="height:220px;"></div>
            </div>
            <div style="border:1px solid #d1d8dd;border-radius:6px;padding:12px;background:#fff;">
                <h4 style="margin:0 0 8px;font-size:13px;font-weight:600;color:#1a2138;">Sales by Pincode</h4>
                <div id="chart-pincode" style="height:220px;"></div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div style="border:1px solid #d1d8dd;border-radius:6px;padding:12px;background:#fff;">
                <h4 style="margin:0 0 8px;font-size:13px;font-weight:600;color:#1a2138;">Period Comparison (Current vs Previous)</h4>
                <div id="chart-period" style="height:220px;"></div>
            </div>
            <div style="border:1px solid #d1d8dd;border-radius:6px;padding:12px;background:#fff;">
                <h4 style="margin:0 0 8px;font-size:13px;font-weight:600;color:#1a2138;">Sales by Item Name</h4>
                <div id="chart-items" style="height:220px;"></div>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px;">
            <div style="border:1px solid #d1d8dd;border-radius:6px;padding:12px;background:#fff;">
                <h4 style="margin:0 0 8px;font-size:13px;font-weight:600;color:#1a2138;">PCS Distribution by Sales Person</h4>
                <div id="chart-sp-pcs" style="height:220px;"></div>
            </div>
            <div style="border:1px solid #d1d8dd;border-radius:6px;padding:12px;background:#fff;">
                <h4 style="margin:0 0 8px;font-size:13px;font-weight:600;color:#1a2138;">Daily Sales Trend</h4>
                <div id="chart-trend" style="height:220px;"></div>
            </div>
        </div>`;
        this.$charts.html(html);

        this._render_sp_amount_chart();
        this._render_pincode_chart();
        this._render_period_chart();
        this._render_items_chart();
        this._render_sp_pcs_chart();
        this._render_trend_chart();
    }

    _render_sp_amount_chart() {
        const c = this.charts.sp_amount;
        if (!c || !c.labels.length) return;
        new frappe.Chart("#chart-sp-amount", {
            data: {
                labels: c.labels,
                datasets: [{ values: c.values }],
                chartTypes: ["donut"],
            },
            colors: ["#4C6EF5", "#12B886", "#F59F00", "#E03131", "#7950F2", "#20C997", "#FD7E14", "#339AF0"],
            height: 200,
            is_navigable: true,
            format_tooltip_x: d => d,
            format_tooltip_y: v => "₹" + v.toLocaleString("en-IN"),
        });
    }

    _render_pincode_chart() {
        const c = this.charts.pincode;
        if (!c || !c.labels.length) return;
        new frappe.Chart("#chart-pincode", {
            data: {
                labels: c.labels,
                datasets: [{ name: "Amount", values: c.amounts, chartType: "bar" }],
            },
            colors: ["#4C6EF5"],
            height: 200,
            is_navigable: true,
            format_tooltip_x: d => d,
            format_tooltip_y: v => "₹" + v.toLocaleString("en-IN"),
        });
    }

    _render_period_chart() {
        const c = this.charts.period_comparison;
        if (!c || !c.labels.length) return;
        new frappe.Chart("#chart-period", {
            data: {
                labels: c.labels,
                datasets: [
                    { name: "Current", values: c.current, chartType: "bar" },
                    { name: "Previous", values: c.previous, chartType: "bar" },
                ],
            },
            colors: ["#4C6EF5", "#ADB5BD"],
            height: 200,
            is_navigable: true,
            format_tooltip_x: d => d,
            format_tooltip_y: v => "₹" + v.toLocaleString("en-IN"),
        });
    }

    _render_items_chart() {
        const c = this.charts.items;
        if (!c || !c.labels.length) return;
        new frappe.Chart("#chart-items", {
            data: {
                labels: c.labels,
                datasets: [{ name: "Amount", values: c.amounts, chartType: "bar" }],
            },
            colors: ["#12B886"],
            height: 200,
            is_navigable: true,
            format_tooltip_x: d => d,
            format_tooltip_y: v => "₹" + v.toLocaleString("en-IN"),
        });
    }

    _render_sp_pcs_chart() {
        const c = this.charts.sp_pcs;
        if (!c || !c.labels.length) return;
        new frappe.Chart("#chart-sp-pcs", {
            data: {
                labels: c.labels,
                datasets: [{ values: c.values }],
                chartTypes: ["donut"],
            },
            colors: ["#F59F00", "#E03131", "#4C6EF5", "#12B886", "#7950F2"],
            height: 200,
            is_navigable: true,
            format_tooltip_y: v => v.toLocaleString("en-IN") + " PCS",
        });
    }

    _render_trend_chart() {
        const c = this.charts.trend;
        if (!c || !c.labels.length) return;
        new frappe.Chart("#chart-trend", {
            data: {
                labels: c.labels,
                datasets: [{ name: "Sales", values: c.values, chartType: "line" }],
            },
            colors: ["#4C6EF5"],
            height: 200,
            is_navigable: true,
            format_tooltip_x: d => d,
            format_tooltip_y: v => "₹" + v.toLocaleString("en-IN"),
        });
    }

    /* ==================== TABLES ==================== */
    render_summary() {
        if (!this.summary.length) { this.$summary.html("<p>No data</p>", this.$summary); return; }
        let html = `<div style="margin-bottom:12px;"><h4 style="margin:0 0 6px;font-size:14px;font-weight:600;">Sales Person Summary</h4>
        <table class="table table-bordered table-sm" style="font-size:11px;">
        <thead><tr>
            <th rowspan="2">Sales Person</th>
            <th rowspan="2">Cust</th>
            <th rowspan="2">Items</th>
            <th rowspan="2">Pincodes</th>
            <th colspan="5" style="text-align:center;background:#d4edda;">Current</th>
            <th colspan="5" style="text-align:center;background:#fff3cd;">Previous</th>
            <th colspan="3" style="text-align:center;background:#cce5ff;">Difference</th>
        </tr><tr>
            <th>Box</th><th>PCS</th><th>Ltr</th><th>Amount</th><th>Inv</th>
            <th>Box</th><th>PCS</th><th>Ltr</th><th>Amount</th><th>Inv</th>
            <th>Ltr</th><th>Amount</th><th>Inv</th>
        </tr></thead><tbody>`;

        let tot = {cb:0,cp:0,cl:0,ca:0,ci:0, pb:0,pp:0,pl:0,pa:0,pi:0 };
        this.summary.forEach(s => {
            const cls = s.diff_amount >= 0 ? "color:#27ae60" : "color:#e74c3c";
            html += `<tr>
                <td><b>${s.sales_person}</b></td>
                <td style="text-align:center">${s.customers}</td>
                <td style="text-align:center">${s.items}</td>
                <td style="text-align:center">${s.pincode_count || 0}</td>
                <td style="text-align:right">${this.fn(s.cur_box)}</td>
                <td style="text-align:right">${this.fn(s.cur_pcs)}</td>
                <td style="text-align:right">${this.fn(s.cur_ltr)}</td>
                <td style="text-align:right;font-weight:700">${this.fn(s.cur_amount)}</td>
                <td style="text-align:center">${s.cur_invoices}</td>
                <td style="text-align:right">${this.fn(s.prev_box)}</td>
                <td style="text-align:right">${this.fn(s.prev_pcs)}</td>
                <td style="text-align:right">${this.fn(s.prev_ltr)}</td>
                <td style="text-align:right">${this.fn(s.prev_amount)}</td>
                <td style="text-align:center">${s.prev_invoices}</td>
                <td style="text-align:right;${cls}">${this.fd(s.diff_ltr,s.pct_ltr)}</td>
                <td style="text-align:right;${cls};font-weight:700">${this.fd(s.diff_amount,s.pct_amount)}</td>
                <td style="text-align:center;${cls}">${s.diff_invoices>=0?"+":""}${s.diff_invoices}</td>
            </tr>`;
            tot.cb+=s.cur_box; tot.cp+=s.cur_pcs; tot.cl+=s.cur_ltr; tot.ca+=s.cur_amount; tot.ci+=s.cur_invoices;
            tot.pb+=s.prev_box; tot.pp+=s.prev_pcs; tot.pl+=s.prev_ltr; tot.pa+=s.prev_amount; tot.pi+=s.prev_invoices;
        });

        const tDiff=tot.ca-tot.pa, tPct=tot.pa?(tDiff/tot.pa*100):(tot.ca?100:0);
        const tLtrDiff=tot.cl-tot.pl, tLtrPct=tot.pl?(tLtrDiff/tot.pl*100):(tot.cl?100:0);
        html += `<tr style="background:#f5f5f5;font-weight:700">
            <td colspan="4">TOTAL</td>
            <td style="text-align:right">${this.fn(tot.cb)}</td><td style="text-align:right">${this.fn(tot.cp)}</td>
            <td style="text-align:right">${this.fn(tot.cl)}</td><td style="text-align:right">${this.fn(tot.ca)}</td>
            <td style="text-align:center">${tot.ci}</td>
            <td style="text-align:right">${this.fn(tot.pb)}</td><td style="text-align:right">${this.fn(tot.pp)}</td>
            <td style="text-align:right">${this.fn(tot.pl)}</td><td style="text-align:right">${this.fn(tot.pa)}</td>
            <td style="text-align:center">${tot.pi}</td>
            <td style="text-align:right;${tLtrDiff>=0?"color:#27ae60":"color:#e74c3c"}">${this.fd(tLtrDiff,tLtrPct)}</td>
            <td style="text-align:right;${tDiff>=0?"color:#27ae60":"color:#e74c3c"}"><b>${this.fd(tDiff,tPct)}</b></td>
            <td style="text-align:center;${tDiff>=0?"color:#27ae60":"color:#e74c3c"}">${tot.ci-tot.pi>=0?"+":""}${tot.ci-tot.pi}</td>
        </tr>`;
        html += "</tbody></table></div>";
        this.$summary.html(html);
    }

    render_pincode_summary() {
        if (!this.pincode_summary.length) { this.$pincode_area.html(""); return; }
        let html = `<div style="margin-bottom:12px;"><h4 style="margin:0 0 6px;font-size:14px;font-weight:600;">Pincode Summary</h4>
        <table class="table table-bordered table-sm" style="font-size:11px;">
        <thead><tr>
            <th rowspan="2">Pincode</th>
            <th rowspan="2">SPs</th>
            <th rowspan="2">Cust</th>
            <th rowspan="2">Items</th>
            <th colspan="5" style="text-align:center;background:#d4edda;">Current</th>
            <th colspan="5" style="text-align:center;background:#fff3cd;">Previous</th>
            <th colspan="3" style="text-align:center;background:#cce5ff;">Difference</th>
        </tr><tr>
            <th>Box</th><th>PCS</th><th>Ltr</th><th>Amount</th><th>Inv</th>
            <th>Box</th><th>PCS</th><th>Ltr</th><th>Amount</th><th>Inv</th>
            <th>Ltr</th><th>Amount</th><th>Inv</th>
        </tr></thead><tbody>`;

        let tot = {cb:0,cp:0,cl:0,ca:0,ci:0, pb:0,pp:0,pl:0,pa:0,pi:0 };
        this.pincode_summary.forEach(s => {
            const cls = s.diff_amount >= 0 ? "color:#27ae60" : "color:#e74c3c";
            html += `<tr>
                <td><b>${s.pincode}</b></td>
                <td style="text-align:center">${s.sales_person_count||0}</td>
                <td style="text-align:center">${s.customer_count||0}</td>
                <td style="text-align:center">${s.item_count||0}</td>
                <td style="text-align:right">${this.fn(s.cur_box)}</td><td style="text-align:right">${this.fn(s.cur_pcs)}</td>
                <td style="text-align:right">${this.fn(s.cur_ltr)}</td><td style="text-align:right;font-weight:700">${this.fn(s.cur_amount)}</td>
                <td style="text-align:center">${s.cur_invoices}</td>
                <td style="text-align:right">${this.fn(s.prev_box)}</td><td style="text-align:right">${this.fn(s.prev_pcs)}</td>
                <td style="text-align:right">${this.fn(s.prev_ltr)}</td><td style="text-align:right">${this.fn(s.prev_amount)}</td>
                <td style="text-align:center">${s.prev_invoices}</td>
                <td style="text-align:right;${cls}">${this.fd(s.diff_ltr,s.pct_ltr)}</td>
                <td style="text-align:right;${cls};font-weight:700">${this.fd(s.diff_amount,s.pct_amount)}</td>
                <td style="text-align:center;${cls}">${s.diff_invoices>=0?"+":""}${s.diff_invoices}</td>
            </tr>`;
            tot.cb+=s.cur_box; tot.cp+=s.cur_pcs; tot.cl+=s.cur_ltr; tot.ca+=s.cur_amount; tot.ci+=s.cur_invoices;
            tot.pb+=s.prev_box; tot.pp+=s.prev_pcs; tot.pl+=s.prev_ltr; tot.pa+=s.prev_amount; tot.pi+=s.prev_invoices;
        });

        const tDiff=tot.ca-tot.pa, tPct=tot.pa?(tDiff/tot.pa*100):(tot.ca?100:0);
        const tLtrDiff=tot.cl-tot.pl, tLtrPct=tot.pl?(tLtrDiff/tot.pl*100):(tot.cl?100:0);
        html += `<tr style="background:#f5f5f5;font-weight:700">
            <td colspan="4">TOTAL</td>
            <td style="text-align:right">${this.fn(tot.cb)}</td><td style="text-align:right">${this.fn(tot.cp)}</td>
            <td style="text-align:right">${this.fn(tot.cl)}</td><td style="text-align:right">${this.fn(tot.ca)}</td>
            <td style="text-align:center">${tot.ci}</td>
            <td style="text-align:right">${this.fn(tot.pb)}</td><td style="text-align:right">${this.fn(tot.pp)}</td>
            <td style="text-align:right">${this.fn(tot.pl)}</td><td style="text-align:right">${this.fn(tot.pa)}</td>
            <td style="text-align:center">${tot.pi}</td>
            <td style="text-align:right;${tLtrDiff>=0?"color:#27ae60":"color:#e74c3c"}">${this.fd(tLtrDiff,tLtrPct)}</td>
            <td style="text-align:right;${tDiff>=0?"color:#27ae60":"color:#e74c3c"}"><b>${this.fd(tDiff,tPct)}</b></td>
            <td style="text-align:center;${tDiff>=0?"color:#27ae60":"color:#e74c3c"}">${tot.ci-tot.pi>=0?"+":""}${tot.ci-tot.pi}</td>
        </tr>`;
        html += "</tbody></table></div>";
        this.$pincode_area.html(html);
    }

    render_sp_pincode_summary() {
        if (!this.sp_pincode_summary.length) { this.$sp_pincode.html(""); return; }
        let html = `<div style="margin-bottom:12px;"><h4 style="margin:0 0 6px;font-size:14px;font-weight:600;">Sales Person + Pincode Summary</h4>
        <table class="table table-bordered table-sm" style="font-size:11px;">
        <thead><tr>
            <th rowspan="2">Sales Person</th><th rowspan="2">Pincode</th>
            <th colspan="5" style="text-align:center;background:#d4edda;">Current</th>
            <th colspan="5" style="text-align:center;background:#fff3cd;">Previous</th>
            <th colspan="3" style="text-align:center;background:#cce5ff;">Difference</th>
        </tr><tr>
            <th>Box</th><th>PCS</th><th>Ltr</th><th>Amount</th><th>Inv</th>
            <th>Box</th><th>PCS</th><th>Ltr</th><th>Amount</th><th>Inv</th>
            <th>Ltr</th><th>Amount</th><th>Inv</th>
        </tr></thead><tbody>`;

        let tot = {cb:0,cp:0,cl:0,ca:0,ci:0, pb:0,pp:0,pl:0,pa:0,pi:0 };
        this.sp_pincode_summary.forEach(s => {
            const cls = s.diff_amount >= 0 ? "color:#27ae60" : "color:#e74c3c";
            html += `<tr>
                <td><b>${s.sales_person}</b></td><td>${s.pincode}</td>
                <td style="text-align:right">${this.fn(s.cur_box)}</td><td style="text-align:right">${this.fn(s.cur_pcs)}</td>
                <td style="text-align:right">${this.fn(s.cur_ltr)}</td><td style="text-align:right;font-weight:700">${this.fn(s.cur_amount)}</td>
                <td style="text-align:center">${s.cur_invoices}</td>
                <td style="text-align:right">${this.fn(s.prev_box)}</td><td style="text-align:right">${this.fn(s.prev_pcs)}</td>
                <td style="text-align:right">${this.fn(s.prev_ltr)}</td><td style="text-align:right">${this.fn(s.prev_amount)}</td>
                <td style="text-align:center">${s.prev_invoices}</td>
                <td style="text-align:right;${cls}">${this.fd(s.diff_ltr,s.pct_ltr)}</td>
                <td style="text-align:right;${cls};font-weight:700">${this.fd(s.diff_amount,s.pct_amount)}</td>
                <td style="text-align:center;${cls}">${s.diff_invoices>=0?"+":""}${s.diff_invoices}</td>
            </tr>`;
            tot.cb+=s.cur_box; tot.cp+=s.cur_pcs; tot.cl+=s.cur_ltr; tot.ca+=s.cur_amount; tot.ci+=s.cur_invoices;
            tot.pb+=s.prev_box; tot.pp+=s.prev_pcs; tot.pl+=s.prev_ltr; tot.pa+=s.prev_amount; tot.pi+=s.prev_invoices;
        });

        const tDiff=tot.ca-tot.pa, tPct=tot.pa?(tDiff/tot.pa*100):(tot.ca?100:0);
        const tLtrDiff=tot.cl-tot.pl, tLtrPct=tot.pl?(tLtrDiff/tot.pl*100):(tot.cl?100:0);
        html += `<tr style="background:#f5f5f5;font-weight:700">
            <td colspan="2">TOTAL</td>
            <td style="text-align:right">${this.fn(tot.cb)}</td><td style="text-align:right">${this.fn(tot.cp)}</td>
            <td style="text-align:right">${this.fn(tot.cl)}</td><td style="text-align:right">${this.fn(tot.ca)}</td>
            <td style="text-align:center">${tot.ci}</td>
            <td style="text-align:right">${this.fn(tot.pb)}</td><td style="text-align:right">${this.fn(tot.pp)}</td>
            <td style="text-align:right">${this.fn(tot.pl)}</td><td style="text-align:right">${this.fn(tot.pa)}</td>
            <td style="text-align:center">${tot.pi}</td>
            <td style="text-align:right;${tLtrDiff>=0?"color:#27ae60":"color:#e74c3c"}">${this.fd(tLtrDiff,tLtrPct)}</td>
            <td style="text-align:right;${tDiff>=0?"color:#27ae60":"color:#e74c3c"}"><b>${this.fd(tDiff,tPct)}</b></td>
            <td style="text-align:center;${tDiff>=0?"color:#27ae60":"color:#e74c3c"}">${tot.ci-tot.pi>=0?"+":""}${tot.ci-tot.pi}</td>
        </tr>`;
        html += "</tbody></table></div>";
        this.$sp_pincode.html(html);
    }

    render_detail() {
        if (!this.data.length) { this.$detail.html(""); return; }
        let html = `<h4 style="margin:0 0 6px;font-size:14px;font-weight:600;">Detailed Breakdown</h4>
        <table class="table table-bordered table-sm" style="font-size:11px;">
        <thead><tr>
            <th>#</th><th>Sales Person</th><th>Pincode</th><th>Customer</th><th>Group</th><th>Item Name</th>
            <th style="text-align:right">Cur Box</th><th style="text-align:right">Cur PCS</th>
            <th style="text-align:right">Cur Ltr</th><th style="text-align:right">Cur Amt</th>
            <th style="text-align:right">Prev Box</th><th style="text-align:right">Prev PCS</th>
            <th style="text-align:right">Prev Ltr</th><th style="text-align:right">Prev Amt</th>
            <th style="text-align:right">Diff Ltr</th><th style="text-align:right">Diff Amt</th>
        </tr></thead><tbody>`;

        this.data.forEach((r, i) => {
            const cls = r.diff_amount >= 0 ? "color:#27ae60" : "color:#e74c3c";
            html += `<tr>
                <td>${i+1}</td><td>${r.sales_person}</td><td>${r.pincode||"-"}</td>
                <td>${r.customer}</td><td>${r.party_group||"-"}</td>
                <td>${r.item_name||"-"}</td>
                <td style="text-align:right">${this.fn(r.cur_box)}</td><td style="text-align:right">${this.fn(r.cur_pcs)}</td>
                <td style="text-align:right">${this.fn(r.cur_ltr)}</td><td style="text-align:right;font-weight:700">${this.fn(r.cur_amount)}</td>
                <td style="text-align:right">${this.fn(r.prev_box)}</td><td style="text-align:right">${this.fn(r.prev_pcs)}</td>
                <td style="text-align:right">${this.fn(r.prev_ltr)}</td><td style="text-align:right">${this.fn(r.prev_amount)}</td>
                <td style="text-align:right;${cls}">${this.fd(r.diff_ltr,r.pct_ltr)}</td>
                <td style="text-align:right;${cls};font-weight:700">${this.fd(r.diff_amount,r.pct_amount)}</td>
            </tr>`;
        });
        html += "</tbody></table>";
        this.$detail.html(html);
    }

    /* ==================== HELPERS ==================== */
    fn(v) { return (v||0).toLocaleString("en-IN", {minimumFractionDigits:2, maximumFractionDigits:2}); }
    fd(diff, pct) { const s = diff>=0?"+":""; const p = Number(pct||0).toFixed(1); return `${s}${this.fn(diff)} (${s}${p}%)`; }

    /* ==================== EXPORT ==================== */
    open_export_dialog() {
        if (!this.data.length) { frappe.msgprint("No data. Run search first."); return; }
        const d = new frappe.ui.Dialog({
            title: "Export Report",
            fields: [{
                label: "Select Breakdown", fieldname: "breakdown", fieldtype: "Select",
                options: ["Sales Person Summary","Pincode Summary","Sales Person + Pincode Summary","Detailed Breakdown","All (Combined CSV)"],
                default: "Sales Person Summary", reqd: 1,
            }],
            primary_action_label: "Download CSV",
            primary_action: (v) => { d.hide(); this.export_csv(v.breakdown); },
        });
        d.show();
    }

    export_csv(breakdown) {
        const fn = `sales_person_report_${this.$from.val()}_to_${this.$to.val()}`;
        let csv = "";
        const sep = (label) => { if (breakdown === "All (Combined CSV)") csv += `=== ${label} ===\n`; };

        if (breakdown === "Sales Person Summary" || breakdown === "All (Combined CSV)") {
            sep("SALES PERSON SUMMARY");
            csv += "Sales Person,Customers,Items,Pincodes,Cur Box,Cur PCS,Cur Ltr,Cur Amount,Cur Invoices,Prev Box,Prev PCS,Prev Ltr,Prev Amount,Prev Invoices,Diff Ltr,Diff Amount,Diff Invoices\n";
            this.summary.forEach(s => {
                csv += `"${s.sales_person}",${s.customers},${s.items},${s.pincode_count||0},${s.cur_box},${s.cur_pcs},${s.cur_ltr},${s.cur_amount},${s.cur_invoices},${s.prev_box},${s.prev_pcs},${s.prev_ltr},${s.prev_amount},${s.prev_invoices},${s.diff_ltr},${s.diff_amount},${s.diff_invoices}\n`;
            });
            csv += "\n";
        }
        if (breakdown === "Pincode Summary" || breakdown === "All (Combined CSV)") {
            sep("PINCODE SUMMARY");
            csv += "Pincode,SPs,Customers,Items,Cur Box,Cur PCS,Cur Ltr,Cur Amount,Cur Invoices,Prev Box,Prev PCS,Prev Ltr,Prev Amount,Prev Invoices,Diff Ltr,Diff Amount,Diff Invoices\n";
            this.pincode_summary.forEach(s => {
                csv += `"${s.pincode}",${s.sales_person_count||0},${s.customer_count||0},${s.item_count||0},${s.cur_box},${s.cur_pcs},${s.cur_ltr},${s.cur_amount},${s.cur_invoices},${s.prev_box},${s.prev_pcs},${s.prev_ltr},${s.prev_amount},${s.prev_invoices},${s.diff_ltr},${s.diff_amount},${s.diff_invoices}\n`;
            });
            csv += "\n";
        }
        if (breakdown === "Sales Person + Pincode Summary" || breakdown === "All (Combined CSV)") {
            sep("SALES PERSON + PINCODE");
            csv += "Sales Person,Pincode,Cur Box,Cur PCS,Cur Ltr,Cur Amount,Cur Invoices,Prev Box,Prev PCS,Prev Ltr,Prev Amount,Prev Invoices,Diff Ltr,Diff Amount,Diff Invoices\n";
            this.sp_pincode_summary.forEach(s => {
                csv += `"${s.sales_person}","${s.pincode}",${s.cur_box},${s.cur_pcs},${s.cur_ltr},${s.cur_amount},${s.cur_invoices},${s.prev_box},${s.prev_pcs},${s.prev_ltr},${s.prev_amount},${s.prev_invoices},${s.diff_ltr},${s.diff_amount},${s.diff_invoices}\n`;
            });
            csv += "\n";
        }
        if (breakdown === "Detailed Breakdown" || breakdown === "All (Combined CSV)") {
            sep("DETAILED BREAKDOWN");
            csv += "#,Sales Person,Pincode,Customer,Group,Item Name,Cur Box,Cur PCS,Cur Ltr,Cur Amt,Prev Box,Prev PCS,Prev Ltr,Prev Amt,Diff Ltr,Diff Amt\n";
            this.data.forEach((r, i) => {
                csv += `${i+1},"${r.sales_person}","${r.pincode||""}","${r.customer}","${r.party_group||""}","${r.item_name||""}",${r.cur_box},${r.cur_pcs},${r.cur_ltr},${r.cur_amount},${r.prev_box},${r.prev_pcs},${r.prev_ltr},${r.prev_amount},${r.diff_ltr},${r.diff_amount}\n`;
            });
        }

        const blob = new Blob([csv], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url; a.download = `${fn}.csv`; a.click();
        URL.revokeObjectURL(url);
    }
};
