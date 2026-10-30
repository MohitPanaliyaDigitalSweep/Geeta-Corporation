frappe.provide("fast_entry_app");

frappe.pages["fast-live-map"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Live Map"), single_column: true });
    fast_entry_app.live_map_page = new fast_entry_app.LiveMap(wrapper);
};

fast_entry_app.LiveMap = class LiveMap {
    constructor(wrapper) {
        this.wrapper = wrapper;
        this.page = wrapper.page;
        this.map = null;
        this.markers = {};
        this.build();
    }

    build() {
        this.$root = $(this.wrapper.page.main);
        this.$root.html(this.get_html());
        this.bind_elements();
        this.load_companies();
        this.init_map();
        this.refresh_locations();
        // Auto-refresh every 30 seconds
        this._interval = setInterval(() => this.refresh_locations(), 30000);
    }

    get_html() {
        return `<div class="fast-entry-container" style="max-width:100%;">
            <div class="fe-header-section">
                <div class="fe-header-row">
                    <div class="fe-field"><label>Company</label><select class="fe-input" id="lm-company"></select></div>
                    <div class="fe-field" style="flex:0 0 120px;align-self:flex-end;"><button class="fe-btn fe-btn-primary" id="lm-refresh" style="width:100%;justify-content:center;"><i class="fa fa-refresh"></i> Refresh</button></div>
                    <div class="fe-field" style="flex:0 0 120px;align-self:flex-end;"><span id="lm-count" style="font-size:12px;color:#6b7280;"></span></div>
                </div>
            </div>
            <div id="lm-map" style="height:600px;border:1px solid #e5e7eb;border-radius:8px;margin-top:10px;"></div>
            <div id="lm-legend" style="margin-top:8px;font-size:11px;color:#6b7280;"></div>
        </div>`;
    }

    bind_elements() {
        const self = this;
        this.$company = this.$root.find("#lm-company");
        this.$root.find("#lm-refresh").on("click", () => this.refresh_locations());
        this.$company.on("change", () => this.refresh_locations());
    }

    load_companies() {
        const self = this;
        frappe.call({ method: "frappe.client.get_list", args: { doctype: "Company", filters: {}, fields: ["name"], limit_page_length: 100 },
            callback: function(r) {
                const companies = r.message || [];
                self.$company.empty().append('<option value="">All Companies</option>');
                companies.forEach(c => self.$company.append(`<option value="${c.name}">${c.name}</option>`));
            }
        });
    }

    init_map() {
        const self = this;
        const mapEl = this.$root.find("#lm-map")[0];
        if (typeof L === "undefined") {
            frappe.require("leaflet.bundle.js", function() {
                frappe.require("leaflet.bundle.css", function() {
                    self._init_leaflet(mapEl);
                });
            });
        } else {
            frappe.require("leaflet.bundle.css", function() {
                self._init_leaflet(mapEl);
            });
        }
    }

    _init_leaflet(mapEl) {
        this.map = L.map(mapEl).setView([20.5937, 78.9629], 5); // India center
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: '&copy; OpenStreetMap contributors',
            maxZoom: 19,
        }).addTo(this.map);
    }

    refresh_locations() {
        const self = this;
        const company = this.$company.val() || "";
        frappe.call({
            method: "fast_entry_app.api.field_visit.get_live_locations",
            args: { company: company || "" },
            callback: function(r) {
                const locations = r.message || [];
                self.$root.find("#lm-count").text(locations.length + " active");
                self.update_markers(locations);
            }
        });
    }

    update_markers(locations) {
        if (!this.map) return;
        const self = this;
        // Remove old markers not in new set
        const newEmps = new Set(locations.map(l => l.employee));
        Object.keys(this.markers).forEach(function(emp) {
            if (!newEmps.has(emp)) {
                self.map.removeLayer(self.markers[emp]);
                delete self.markers[emp];
            }
        });
        // Add/update markers
        const bounds = [];
        locations.forEach(function(loc) {
            const lat = parseFloat(loc.latitude);
            const lng = parseFloat(loc.longitude);
            if (isNaN(lat) || isNaN(lng)) return;
            bounds.push([lat, lng]);
            const popup = `<b>${self.esc(loc.employee_name || loc.employee)}</b><br>` +
                `<small>${self.esc(loc.company || "")}</small><br>` +
                (loc.party_name ? `Visiting: ${self.esc(loc.party_name)}<br>` : "") +
                (loc.remarks ? `Remarks: ${self.esc(loc.remarks)}<br>` : "") +
                `<small>${loc.visit_date || ""} ${loc.visit_time || ""}</small>`;
            if (self.markers[loc.employee]) {
                self.markers[loc.employee].setLatLng([lat, lng]);
                self.markers[loc.employee].setPopupContent(popup);
            } else {
                const marker = L.marker([lat, lng]).addTo(self.map);
                marker.bindPopup(popup);
                self.markers[loc.employee] = marker;
            }
        });
        if (bounds.length > 0 && bounds.length <= 50) {
            try { self.map.fitBounds(bounds, { padding: [30, 30], maxZoom: 14 }); } catch(e) {}
        }
    }

    destroy() {
        if (this._interval) clearInterval(this._interval);
        if (this.map) this.map.remove();
    }
};