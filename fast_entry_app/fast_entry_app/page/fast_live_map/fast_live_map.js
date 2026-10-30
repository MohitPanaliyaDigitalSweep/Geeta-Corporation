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
        this.employees = [];
        this.build();
    }

    build() {
        this.$root = $(this.wrapper.page.main);
        this.$root.html(this.get_html());
        this.bind_elements();
        this.load_companies();
        this.load_employees();
        this.init_map();
        this.refresh_locations();
        this._interval = setInterval(() => this.refresh_locations(), 30000);
    }

    get_html() {
        return `<div class="fast-entry-container" style="max-width:100%;">
            <div class="fe-header-section">
                <div class="fe-header-row">
                    <div class="fe-field"><label>Company</label><select class="fe-input" id="lm-company"></select></div>
                    <div class="fe-field"><label>Employee</label><select class="fe-input" id="lm-employee"><option value="">All Employees</option></select></div>
                    <div class="fe-field"><label>From Date</label><input type="date" class="fe-input" id="lm-from" /></div>
                    <div class="fe-field"><label>To Date</label><input type="date" class="fe-input" id="lm-to" /></div>
                    <div class="fe-field" style="flex:0 0 140px;align-self:flex-end;"><button class="fe-btn fe-btn-primary" id="lm-track" style="width:100%;justify-content:center;"><i class="fa fa-location-arrow"></i> Start Tracking</button></div>
                <div class="fe-field" style="flex:0 0 120px;align-self:flex-end;"><button class="fe-btn fe-btn-sm" id="lm-refresh" style="width:100%;justify-content:center;"><i class="fa fa-refresh"></i> Refresh</button></div>
                    <div class="fe-field" style="flex:0 0 120px;align-self:flex-end;"><span id="lm-count" style="font-size:12px;color:#6b7280;"></span></div>
                </div>
            </div>
            <div id="lm-map" style="height:600px;border:1px solid #e5e7eb;border-radius:8px;margin-top:10px;"></div>
            <div id="lm-legend" style="margin-top:8px;font-size:11px;color:#6b7280;"></div>
            <div class="fe-card" style="margin-top:12px;">
                <div class="fe-card-header"><i class="fa fa-list"></i> Recent Visits <span id="lm-visit-count" style="font-size:11px;color:#6b7280;margin-left:8px;"></span></div>
                <div id="lm-visit-list" style="max-height:300px;overflow-y:auto;">
                    <div style="text-align:center;padding:20px;color:#9ca3af;">Loading...</div>
                </div>
            </div>
        </div>`;
    }

    bind_elements() {
        const self = this;
        this.$company = this.$root.find("#lm-company");
        this.$employee = this.$root.find("#lm-employee");
        this.$from = this.$root.find("#lm-from");
        this.$to = this.$root.find("#lm-to");
        this.$track = this.$root.find("#lm-track");
        this.$root.find("#lm-refresh").on("click", () => this.refresh_locations());
        this.$company.on("change", () => { this.load_employees(); this.refresh_locations(); });
        this.$employee.on("change", () => this.refresh_locations());
        this.$from.on("change", () => this.refresh_locations());
        this.$to.on("change", () => this.refresh_locations());
        this.$track.on("click", () => this.toggle_tracking());
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

    load_employees() {
        const self = this;
        const company = this.$company.val() || "";
        frappe.call({ method: "fast_entry_app.api.field_visit.get_employees", args: { company: company },
            callback: function(r) {
                const emps = r.message || [];
                self.employees = emps;
                self.$employee.empty().append('<option value="">All Employees</option>');
                emps.forEach(e => self.$employee.append(`<option value="${e.name}">${e.employee_name || e.name}</option>`));
            }
        });
    }

    init_map() {
        const self = this;
        const mapEl = this.$root.find("#lm-map")[0];
        const doInit = function() {
            self.map = L.map(mapEl).setView([20.5937, 78.9629], 5);
            L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
                attribution: '&copy; OpenStreetMap contributors',
                maxZoom: 19,
            }).addTo(self.map);
            self.refresh_locations();
        };
        if (typeof L === "undefined") {
            frappe.require("leaflet.bundle.js", function() {
                frappe.require("leaflet.bundle.css", function() { doInit(); });
            });
        } else {
            frappe.require("leaflet.bundle.css", function() { doInit(); });
        }
    }

    refresh_locations() {
        const self = this;
        const company = this.$company.val() || "";
        const employee = this.$employee.val() || "";
        frappe.call({
            method: "fast_entry_app.api.field_visit.get_live_locations",
            args: { company: company },
            callback: function(r) {
                let locations = r.message || [];
                if (employee) locations = locations.filter(l => l.employee === employee);
                self.$root.find("#lm-count").text(locations.length + " active");
                self.update_markers(locations);
                self.load_recent_visits(company, employee);
            }
        });
    }

    update_markers(locations) {
        if (!this.map) return;
        const self = this;
        const newEmps = new Set(locations.map(l => l.employee));
        Object.keys(this.markers).forEach(function(emp) {
            if (!newEmps.has(emp)) {
                self.map.removeLayer(self.markers[emp]);
                delete self.markers[emp];
            }
        });
        const bounds = [];
        locations.forEach(function(loc) {
            const lat = parseFloat(loc.latitude);
            const lng = parseFloat(loc.longitude);
            if (isNaN(lat) || isNaN(lng)) return;
            bounds.push([lat, lng]);
            const popup = `<div style="min-width:180px;">
                <b style="font-size:13px;">${self.esc(loc.employee_name || loc.employee)}</b><br>
                <small style="color:#6b7280;">${self.esc(loc.company || "")}</small><br>
                ${loc.party_name ? `<div style="margin-top:4px;"><i class="fa fa-user"></i> ${self.esc(loc.party_name)}</div>` : ""}
                ${loc.remarks ? `<div style="margin-top:2px;font-size:12px;">${self.esc(loc.remarks)}</div>` : ""}
                <div style="margin-top:4px;font-size:10px;color:#9ca3af;"><i class="fa fa-clock-o"></i> ${loc.visit_date || ""} ${loc.visit_time || ""}</div>
            </div>`;
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
        // Update legend
        const legend = locations.length
            ? `${locations.length} employee${locations.length === 1 ? "" : "s"} tracked`
            : "No active locations";
        self.$root.find("#lm-legend").text(legend);
    }

    load_recent_visits(company, employee) {
        const self = this;
        frappe.call({
            method: "fast_entry_app.api.field_visit.get_field_visits",
            args: { company: company || "", employee: employee || "", limit: 30 },
            callback: function(r) {
                const visits = r.message || [];
                self.$root.find("#lm-visit-count").text(visits.length + " visits");
                let html = "";
                if (!visits.length) {
                    html = '<div style="text-align:center;padding:20px;color:#9ca3af;">No visits found.</div>';
                } else {
                    visits.forEach(function(v) {
                        const photo_html = v.photo ? `<img src="${v.photo}" style="width:40px;height:40px;object-fit:cover;border-radius:4px;margin-right:8px;" />` : `<div style="width:40px;height:40px;background:#f3f4f6;border-radius:4px;margin-right:8px;display:flex;align-items:center;justify-content:center;"><i class="fa fa-map-marker" style="color:#9ca3af;"></i></div>`;
                        html += `<div style="display:flex;align-items:center;padding:8px;border-bottom:1px solid #f3f4f6;gap:8px;">
                            ${photo_html}
                            <div style="flex:1;">
                                <div style="font-weight:600;font-size:12px;">${self.esc(v.employee_name || v.employee)} &mdash; ${self.esc(v.visit_type)}</div>
                                <div style="font-size:11px;color:#6b7280;">${v.visit_date || ""} ${v.visit_time || ""} ${v.party_name ? "&middot; " + self.esc(v.party_name) : ""}</div>
                                ${v.remarks ? `<div style="font-size:11px;color:#374151;margin-top:2px;">${self.esc(v.remarks)}</div>` : ""}
                            </div>
                            ${v.latitude ? `<a href="https://www.google.com/maps?q=${v.latitude},${v.longitude}" target="_blank" style="font-size:11px;color:#3b82f6;"><i class="fa fa-external-link"></i> Map</a>` : ""}
                        </div>`;
                    });
                }
                self.$root.find("#lm-visit-list").html(html);
            }
        });
    }

    toggle_tracking() {
        const self = this;
        if (this._tracking) {
            // Stop tracking
            if (this._watchId) navigator.geolocation.clearWatch(this._watchId);
            this._watchId = null;
            this._tracking = false;
            this.$track.html('<i class="fa fa-location-arrow"></i> Start Tracking').removeClass("fe-btn-danger").addClass("fe-btn-primary");
            frappe.show_alert({ message: __("Location tracking stopped"), indicator: "orange" });
            return;
        }
        if (!navigator.geolocation) {
            frappe.msgprint({ title: "Not Supported", indicator: "red", message: "Geolocation is not supported by this browser." });
            return;
        }
        this._tracking = true;
        this.$track.html('<i class="fa fa-stop"></i> Stop Tracking').removeClass("fe-btn-primary").addClass("fe-btn-danger");
        frappe.show_alert({ message: __("Location tracking started"), indicator: "green" });

        this._watchId = navigator.geolocation.watchPosition(
            function(pos) {
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                const acc = pos.coords.accuracy;
                frappe.call({
                    method: "fast_entry_app.api.location.ping_location",
                    args: { latitude: lat, longitude: lng, accuracy: acc },
                    callback: function(r) {
                        if (r.message && r.message.status === "ok") {
                            self.refresh_locations();
                        }
                    },
                });
            },
            function(err) {
                frappe.msgprint({ title: "Location Error", indicator: "red", message: err.message });
                self.toggle_tracking();
            },
            { enableHighAccuracy: true, timeout: 30000, maximumAge: 60000 }
        );
    }

    destroy() {
        if (this._interval) clearInterval(this._interval);
        if (this._watchId) navigator.geolocation.clearWatch(this._watchId);
        if (this.map) this.map.remove();
    }
};