frappe.provide("fast_entry_app.report_ui");

/* ═══════════ MULTI-SELECT DROPDOWN ═══════════ */
fast_entry_app.report_ui.MultiSelect = class MultiSelect {
    constructor({ container, options, onChange, defaultSelected, placeholder }) {
        this.$container = $(container);
        this.options = options || [];
        this.selected = defaultSelected || this.options.map(o => o.value);
        this.onChange = onChange;
        this.placeholder = placeholder || "All";
        this.render();
    }

    render() {
        const id = "ms-" + frappe.utils.get_random(6);
        this.$container.html(`
            <div class="frms-multi-select" id="${id}">
                <button class="frms-ms-btn" type="button">
                    <span class="frms-ms-label">${this.placeholder}</span>
                    <span class="frms-ms-caret">&#9662;</span>
                </button>
            </div>
        `);
        this.$panel = $(`<div class="frms-ms-panel" id="${id}-panel"></div>`).appendTo("body");
        this.$panel.html(`
            <div class="frms-ms-search-wrap">
                <input class="frms-ms-search" type="text" placeholder="Search..." />
            </div>
            <div class="frms-ms-actions">
                <button class="frms-ms-action" data-action="all">Select All</button>
                <button class="frms-ms-action" data-action="clear">Clear</button>
            </div>
            <div class="frms-ms-opts"></div>
        `);
        this.$el = this.$container.find(".frms-multi-select");
        this.render_opts();
        this.bind();
        this.update_label();
    }

    render_opts() {
        const sel = this.selected;
        const $opts = this.$panel.find(".frms-ms-opts");
        let html = "";
        this.options.forEach(o => {
            const checked = sel.indexOf(o.value) !== -1 ? "checked" : "";
            html += `<label class="frms-ms-opt">
                <input type="checkbox" value="${o.value}" ${checked} />
                <span>${o.label || o.value}</span>
            </label>`;
        });
        $opts.html(html);
    }

    bind() {
        const self = this;
        this.$el.find(".frms-ms-btn").on("click", function (e) {
            e.stopPropagation();
            const $btn = $(this);
            if (self.$panel.hasClass("show")) {
                self.$panel.removeClass("show");
                $btn.removeClass("active");
            } else {
                const rect = $btn[0].getBoundingClientRect();
                self.$panel.addClass("show").css({
                    left: rect.left + "px",
                    top: (rect.bottom + 4) + "px",
                });
                $btn.addClass("active");
                self.$panel.find(".frms-ms-search").val("").focus();
                self.$panel.find(".frms-ms-opt").show();
            }
        });

        $(document).on("click", function (e) {
            if (!self.$el[0].contains(e.target) && !self.$panel[0].contains(e.target)) {
                self.$panel.removeClass("show");
                self.$el.find(".frms-ms-btn").removeClass("active");
            }
        });

        this.$panel.find(".frms-ms-search").on("input", function () {
            const q = this.value.toLowerCase();
            self.$panel.find(".frms-ms-opt").each(function () {
                const txt = $(this).text().toLowerCase();
                $(this).toggle(txt.indexOf(q) !== -1);
            });
        });

        this.$panel.find(".frms-ms-action").on("click", function (e) {
            e.preventDefault();
            const action = $(this).data("action");
            if (action === "all") {
                self.selected = self.options.map(o => o.value);
            } else if (action === "clear") {
                if (self.selected.length <= 1) {
                    frappe.show_alert({ message: "Select at least one", indicator: "orange" });
                    return;
                }
                self.selected = [self.selected[0]];
            }
            self.render_opts();
            self.update_label();
            if (self.onChange) self.onChange(self.selected);
        });

        this.$panel.on("change", ".frms-ms-opt input", function () {
            const val = this.value;
            if (this.checked) {
                if (self.selected.indexOf(val) === -1) self.selected.push(val);
            } else {
                if (self.selected.length <= 1) {
                    this.checked = true;
                    frappe.show_alert({ message: "Select at least one", indicator: "orange" });
                    return;
                }
                self.selected = self.selected.filter(v => v !== val);
            }
            self.update_label();
            if (self.onChange) self.onChange(self.selected);
        });
    }

    update_label() {
        const allSelected = this.selected.length === this.options.length;
        const $label = this.$el.find(".frms-ms-label");
        if (allSelected || this.selected.length === 0) {
            $label.text(this.placeholder);
        } else if (this.selected.length === 1) {
            const opt = this.options.find(o => o.value === this.selected[0]);
            $label.text(opt ? (opt.label || opt.value) : this.selected[0]);
        } else {
            $label.text(this.selected.length + " selected");
        }
    }

    getSelected() { return this.selected.slice(); }
    setOptions(options) {
        this.options = options;
        this.selected = options.map(o => o.value);
        this.render_opts();
        this.update_label();
    }
};

/* ═══════════ PERIOD CHIPS ═══════════ */
fast_entry_app.report_ui.PeriodChips = class PeriodChips {
    constructor({ container, periods, onChange, activePeriod }) {
        this.$container = $(container);
        this.periods = periods || [];
        this.active = activePeriod || (this.periods.length ? this.periods[0].value : "");
        this.onChange = onChange;
        this.render();
    }

    render() {
        let html = '<div class="frms-period-chips">';
        this.periods.forEach(p => {
            const cls = p.value === this.active ? " active" : "";
            html += `<button class="frms-period-chip${cls}" data-value="${p.value}">${p.label}</button>`;
        });
        html += '</div>';
        this.$container.html(html);
        const self = this;
        this.$container.find(".frms-period-chip").on("click", function () {
            self.$container.find(".frms-period-chip").removeClass("active");
            $(this).addClass("active");
            self.active = $(this).data("value");
            if (self.onChange) self.onChange(self.active);
        });
    }

    getActive() { return this.active; }
};

/* ═══════════ COMPARE DROPDOWN ═══════════ */
fast_entry_app.report_ui.CompareDropdown = class CompareDropdown {
    constructor({ container, options, onChange, placeholder }) {
        this.$container = $(container);
        this.options = options || [];
        this.value = "";
        this.onChange = onChange;
        this.placeholder = placeholder || "vs:";
        this.render();
    }

    render() {
        const id = "cmp-" + frappe.utils.get_random(6);
        this.$container.html(`
            <div class="frms-compare" id="${id}">
                <button class="frms-cmp-btn" type="button">
                    <span class="frms-cmp-label">${this.placeholder}</span>
                    <span class="frms-cmp-caret">&#9662;</span>
                </button>
            </div>
        `);
        this.$panel = $(`<div class="frms-cmp-panel" id="${id}-panel"></div>`).appendTo("body");
        this.$el = this.$container.find(".frms-compare");
        this.render_opts();
        this.bind();
    }

    render_opts() {
        let html = `<div class="frms-cmp-opt${this.value === "" ? " selected" : ""}" data-value="">None</div>`;
        this.options.forEach(o => {
            const cls = o.value === this.value ? " selected" : "";
            html += `<div class="frms-cmp-opt${cls}" data-value="${o.value}">${o.label}</div>`;
        });
        this.$panel.html(html);
    }

    bind() {
        const self = this;
        this.$el.find(".frms-cmp-btn").on("click", function (e) {
            e.stopPropagation();
            const $btn = $(this);
            if (self.$panel.hasClass("show")) {
                self.$panel.removeClass("show");
            } else {
                const rect = $btn[0].getBoundingClientRect();
                self.$panel.addClass("show").css({
                    left: rect.left + "px",
                    top: (rect.bottom + 4) + "px",
                });
            }
        });

        $(document).on("click", function (e) {
            if (!self.$el[0].contains(e.target) && !self.$panel[0].contains(e.target)) {
                self.$panel.removeClass("show");
            }
        });

        this.$panel.on("click", ".frms-cmp-opt", function () {
            self.value = $(this).data("value");
            self.$el.find(".frms-cmp-label").text(
                self.value === "" ? self.placeholder : $(this).text()
            );
            self.render_opts();
            self.$panel.removeClass("show");
            if (self.onChange) self.onChange(self.value);
        });
    }

    getValue() { return this.value; }
    setValue(v) {
        this.value = v;
        const opt = this.options.find(o => o.value === v);
        this.$el.find(".frms-cmp-label").text(opt ? opt.label : this.placeholder);
        this.render_opts();
    }
};

/* ═══════════ KPI CARDS ═══════════ */
fast_entry_app.report_ui.render_kpis = function (container, kpis, opts) {
    opts = opts || {};
    const $el = $(container);
    if (!kpis || !kpis.length) { $el.html(""); return; }

    const pct = (cur, prev) => {
        if (!prev) return cur ? "+100.0%" : "0.0%";
        const d = ((cur - prev) / prev * 100);
        return (d >= 0 ? "+" : "") + d.toFixed(1) + "%";
    };
    const cls = (cur, prev) => cur >= prev ? "color:#059669" : "color:#dc2626";
    const arrow = (cur, prev) => cur >= prev ? "&#9650;" : "&#9660;";
    const fmt = v => (v || 0).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const icons = opts.icons || {};

    let html = '<div class="frms-kpi-grid">';
    kpis.forEach(k => {
        const icon = icons[k.label] || k.icon || "fa-chart-bar";
        const curVal = k.cur_value;
        const prevVal = k.prev_value;
        const pctVal = pct(curVal, prevVal);
        const clsVal = cls(curVal, prevVal);
        const arrowVal = arrow(curVal, prevVal);

        html += `<div class="frms-kpi-card">
            <div class="frms-kpi-icon"><i class="fa ${icon}"></i></div>
            <div class="frms-kpi-info">
                <div class="frms-kpi-val">${fmt(curVal)}</div>
                <div class="frms-kpi-lbl">${k.label}</div>
                <div class="frms-kpi-change" style="${clsVal}">
                    ${arrowVal} ${pctVal} <span class="frms-kpi-prev">vs ${fmt(prevVal)}</span>
                </div>
            </div>
            <div class="frms-kpi-spark">${k.sparkline ? fast_entry_app.report_ui.sparkline_svg(k.sparkline, clsVal.includes("#059669") ? "#059669" : "#dc2626") : ""}</div>
        </div>`;
    });
    html += '</div>';
    $el.html(html);
};

/* ═══════════ SPARKLINE SVG ═══════════ */
fast_entry_app.report_ui.sparkline_svg = function (values, color) {
    if (!values || values.length < 2) return "";
    const w = 80, h = 28, p = 4;
    const mx = Math.max(...values) || 1;
    const mn = Math.min(...values);
    const range = mx - mn || 1;
    const pts = values.map((v, i) => ({
        x: p + (i / (values.length - 1)) * (w - 2 * p),
        y: p + (h - 2 * p) - ((v - mn) / range) * (h - 2 * p),
    }));
    const path = pts.map((pt, i) => (i === 0 ? "M" : "L") + ` ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`).join(" ");
    return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">
        <path d="${path}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
};

/* ═══════════ TABLE BUILDER ═══════════ */
fast_entry_app.report_ui.render_table = function (container, headers, rows, opts) {
    opts = opts || {};
    const $el = $(container);
    if (!rows || !rows.length) { $el.html('<div style="padding:20px;text-align:center;color:#8d99a6;">No data found</div>'); return; }

    let html = '<div class="frms-table-wrap"><table class="frms-table"><thead><tr>';
    headers.forEach(h => {
        const align = h.align || "left";
        const w = h.width ? ` style="width:${h.width}"` : "";
        html += `<th${w} style="text-align:${align}">${h.label}</th>`;
    });
    html += '</tr></thead><tbody>';

    rows.forEach(row => {
        html += '<tr>';
        headers.forEach(h => {
            const val = row[h.key] || "";
            const align = h.align || "left";
            const cls = h.cls ? ` class="${h.cls}"` : "";
            html += `<td style="text-align:${align}"${cls}>${val}</td>`;
        });
        html += '</tr>';
    });
    html += '</tbody></table></div>';
    $el.html(html);
};

/* ═══════════ CSV EXPORT ═══════════ */
fast_entry_app.report_ui.export_csv = function (headers, rows, filename) {
    let csv = headers.map(h => `"${h.label}"`).join(",") + "\n";
    rows.forEach(row => {
        csv += headers.map(h => {
            let v = (row[h.key] || "").toString().replace(/"/g, '""');
            return `"${v}"`;
        }).join(",") + "\n";
    });
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = (filename || "report") + ".csv";
    link.click();
};

/* ═══════════ CHART HELPERS ═══════════ */
fast_entry_app.report_ui._charts = {};

fast_entry_app.report_ui._destroy_chart = function (container) {
    const sel = typeof container === "string" ? container : null;
    if (sel && fast_entry_app.report_ui._charts[sel]) {
        try { fast_entry_app.report_ui._charts[sel].destroy(); } catch(e) {}
        delete fast_entry_app.report_ui._charts[sel];
    }
    if (sel) {
        const el = document.querySelector(sel);
        if (el) el.innerHTML = "";
    }
};

fast_entry_app.report_ui.render_donut = function (container, labels, values, colors) {
    if (!labels || !labels.length) return;
    fast_entry_app.report_ui._destroy_chart(container);
    colors = colors || ["#4C6EF5", "#12B886", "#F59F00", "#E03131", "#7950F2", "#20C997", "#FD7E14", "#339AF0"];
    const el = document.querySelector(container);
    if (!el) return;
    const chart = new frappe.Chart(el, {
        data: { labels, datasets: [{ values }] },
        type: "donut",
        colors,
        height: 220,
        is_navigable: true,
        format_tooltip_x: d => d,
        format_tooltip_y: v => "₹" + v.toLocaleString("en-IN"),
    });
    fast_entry_app.report_ui._charts[container] = chart;
};

fast_entry_app.report_ui.render_bar = function (container, labels, values, opts) {
    opts = opts || {};
    if (!labels || !labels.length) return;
    fast_entry_app.report_ui._destroy_chart(container);
    const el = document.querySelector(container);
    if (!el) return;
    const chart = new frappe.Chart(el, {
        data: { labels, datasets: [{ values: values.map(v => parseFloat(v) || 0) }] },
        type: "bar",
        height: opts.height || 220,
        barOptions: { stacked: opts.stacked || false },
        format_tooltip_x: d => d,
        format_tooltip_y: v => opts.currency ? "₹" + v.toLocaleString("en-IN") : v.toLocaleString("en-IN"),
    });
    fast_entry_app.report_ui._charts[container] = chart;
};

fast_entry_app.report_ui.render_grouped_bar = function (container, labels, datasets, opts) {
    opts = opts || {};
    if (!labels || !labels.length) return;
    fast_entry_app.report_ui._destroy_chart(container);
    const colors = ["#4C6EF5", "#E03131", "#12B886", "#F59F00"];
    const el = document.querySelector(container);
    if (!el) return;
    const chart = new frappe.Chart(el, {
        data: { labels, datasets },
        type: "bar",
        height: opts.height || 220,
        colors,
        format_tooltip_x: d => d,
        format_tooltip_y: v => opts.currency ? "₹" + v.toLocaleString("en-IN") : v.toLocaleString("en-IN"),
    });
    fast_entry_app.report_ui._charts[container] = chart;
};

fast_entry_app.report_ui.render_line = function (container, labels, values, opts) {
    opts = opts || {};
    if (!labels || !labels.length) return;
    fast_entry_app.report_ui._destroy_chart(container);
    const el = document.querySelector(container);
    if (!el) return;
    const chart = new frappe.Chart(el, {
        data: { labels, datasets: [{ values: values.map(v => parseFloat(v) || 0) }] },
        type: "line",
        height: opts.height || 220,
        lineOptions: { dotSize: 4, hideDots: 0 },
        format_tooltip_x: d => d,
        format_tooltip_y: v => opts.currency ? "₹" + v.toLocaleString("en-IN") : v.toLocaleString("en-IN"),
    });
    fast_entry_app.report_ui._charts[container] = chart;
};
