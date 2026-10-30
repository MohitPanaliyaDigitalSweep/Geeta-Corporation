frappe.provide("fast_entry_app");

frappe.pages["fast-field-visit"].on_page_load = function (wrapper) {
    frappe.ui.make_app_page({ parent: wrapper, title: __("Field Visit"), single_column: true });
    fast_entry_app.field_visit_page = new fast_entry_app.FieldVisit(wrapper);
};

fast_entry_app.FieldVisit = class FieldVisit {
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
        this.load_employees();
    }

    get_html() {
        const today = frappe.datetime.get_today();
        return `<div class="fast-entry-container" style="max-width:600px;margin:0 auto;">
            <div class="fe-card">
                <div class="fe-card-header"><i class="fa fa-map-marker"></i> Log Field Visit</div>
                <div class="fe-header-section">
                    <div class="fe-header-row">
                        <div class="fe-field"><label>Employee <span class="reqd">*</span></label><select class="fe-input" id="fv-employee"></select></div>
                        <div class="fe-field"><label>Company</label><select class="fe-input" id="fv-company"></select></div>
                    </div>
                    <div class="fe-header-row">
                        <div class="fe-field"><label>Visit Date</label><input type="date" class="fe-input" id="fv-date" value="${today}" /></div>
                        <div class="fe-field"><label>Visit Time</label><input type="time" class="fe-input" id="fv-time" /></div>
                    </div>
                    <div class="fe-header-row">
                        <div class="fe-field"><label>Party Type</label>
                            <select class="fe-input" id="fv-party-type">
                                <option value="Customer">Customer</option>
                                <option value="Supplier">Supplier</option>
                                <option value="Lead">Lead</option>
                                <option value="None">None</option>
                            </select>
                        </div>
                        <div class="fe-field fe-field-wide"><label>Party</label><div class="fe-input-wrap fe-autocomplete-wrap"><input type="text" class="fe-input" id="fv-party" placeholder="Search..." autocomplete="off" /></div></div>
                    </div>
                    <div class="fe-header-row">
                        <div class="fe-field"><label>Visit Type</label>
                            <select class="fe-input" id="fv-visit-type">
                                <option value="Customer Visit">Customer Visit</option>
                                <option value="Site Survey">Site Survey</option>
                                <option value="Delivery Follow-up">Delivery Follow-up</option>
                                <option value="Collection">Collection</option>
                                <option value="Other">Other</option>
                            </select>
                        </div>
                    </div>
                </div>
            </div>

            <div class="fe-card">
                <div class="fe-card-header"><i class="fa fa-map-marker"></i> Location</div>
                <div style="margin-bottom:10px;">
                    <button class="fe-btn fe-btn-primary" id="fv-get-location" style="width:100%;justify-content:center;"><i class="fa fa-crosshairs"></i> Capture Current Location</button>
                </div>
                <div id="fv-location-status" style="font-size:12px;color:#6b7280;margin-bottom:8px;">No location captured yet.</div>
                <div id="fv-map" style="height:250px;border:1px solid #e5e7eb;border-radius:6px;display:none;"></div>
                <input type="hidden" id="fv-lat" />
                <input type="hidden" id="fv-lng" />
                <input type="hidden" id="fv-geolocation" />
            </div>

            <div class="fe-card">
                <div class="fe-card-header"><i class="fa fa-camera"></i> Photo & Remarks</div>
                <div style="margin-bottom:10px;">
                    <label style="font-size:12px;font-weight:600;color:#374151;display:block;margin-bottom:4px;">Photo</label>
                    <input type="file" id="fv-photo" accept="image/*" capture="environment" class="fe-input" style="padding:4px;" />
                    <div id="fv-photo-preview" style="margin-top:8px;display:none;">
                        <img id="fv-photo-img" style="max-width:100%;max-height:200px;border-radius:6px;border:1px solid #e5e7eb;" />
                    </div>
                </div>
                <div class="fe-field">
                    <label>Remarks</label>
                    <textarea class="fe-input" id="fv-remarks" rows="3" placeholder="Notes about this visit..."></textarea>
                </div>
            </div>

            <div style="display:flex;gap:10px;margin-top:10px;">
                <button class="fe-btn fe-btn-primary" id="fv-save" style="flex:1;justify-content:center;"><i class="fa fa-save"></i> Save Visit</button>
                <button class="fe-btn fe-btn-sm" id="fv-save-draft" style="flex:0 0 140px;justify-content:center;"><i class="fa fa-file-o"></i> Save as Draft</button>
            </div>

            <div class="fe-status-bar" id="fv-status-bar"></div>

            <div class="fe-card" style="margin-top:16px;">
                <div class="fe-card-header"><i class="fa fa-list"></i> Recent Visits</div>
                <div id="fv-recent-list" style="max-height:300px;overflow-y:auto;">
                    <div style="text-align:center;padding:20px;color:#9ca3af;"><i class="fa fa-spinner fa-spin"></i> Loading...</div>
                </div>
            </div>
        </div>`;
    }

    bind_elements() {
        const self = this;
        this.$company = this.$root.find("#fv-company");
        this.$employee = this.$root.find("#fv-employee");
        this.$party_type = this.$root.find("#fv-party-type");
        this.$party = this.$root.find("#fv-party");
        this.$party_name = this.$root.find("#fv-party-name");
        this.$status_bar = this.$root.find("#fv-status-bar");

        this.$root.find("#fv-get-location").on("click", () => this.capture_location());
        this.$root.find("#fv-photo").on("change", (e) => this.preview_photo(e));
        this.$root.find("#fv-save").on("click", () => this.save(false));
        this.$root.find("#fv-save-draft").on("click", () => this.save(true));

        this.$party.on("input", function() {
            const val = $(this).val();
            if (val.length < 1) { self.hide_dropdown(); return; }
            const pt = self.$party_type.val();
            const method = pt === "Customer" ? "fast_entry_app.api.field_visit.get_customers" :
                           pt === "Supplier" ? "fast_entry_app.api.field_visit.get_suppliers" : null;
            if (!method) return;
            frappe.call({ method: method, args: { search: val, limit: 10 }, callback: function(r) {
                const items = r.message || [];
                let html = "";
                items.forEach(function(item) {
                    const name = item.customer_name || item.supplier_name || item.name;
                    html += `<div class="fe-dropdown-item" data-value="${item.name}" data-name="${name}"><span class="fe-dd-primary">${name}</span><span class="fe-dd-secondary">${item.name}</span></div>`;
                });
                if (html) {
                    const $dd = self.show_dropdown(self.$party, html, function($el) {
                        self.$party.val($el.data("name")).attr("data-party", $el.data("value"));
                        self.$party_name.val($el.data("name"));
                        self.hide_dropdown();
                    });
                } else {
                    self.hide_dropdown();
                }
            }});
        });

        this.load_recent_visits();
    }

    show_dropdown($input, html, select_handler) {
        this.hide_dropdown();
        const $dd = $('<div class="fe-global-dropdown"></div>').appendTo("body").html(html).show();
        const rect = $input[0].getBoundingClientRect();
        $dd.css({ top: rect.bottom + 1, left: rect.left, width: Math.max(rect.width, 250) });
        $dd.on("mousedown", ".fe-dropdown-item", (e) => {
            e.preventDefault();
            select_handler($(e.currentTarget));
        });
        this.$dd = $dd;
        return $dd;
    }

    hide_dropdown() { if (this.$dd) { this.$dd.hide().remove(); this.$dd = null; } }

    load_companies() {
        const self = this;
        frappe.call({ method: "frappe.client.get_list", args: { doctype: "Company", filters: {}, fields: ["name"], limit_page_length: 100 },
            callback: function(r) {
                const companies = r.message || [];
                self.$company = self.$root.find("#fv-company");
                self.$company.empty().append('<option value="">Select Company</option>');
                companies.forEach(c => self.$company.append(`<option value="${c.name}">${c.name}</option>`));
                if (companies.length === 1) self.$company.val(companies[0].name);
            }
        });
    }

    load_employees() {
        const self = this;
        frappe.call({ method: "fast_entry_app.api.field_visit.get_employees", args: { company: "" },
            callback: function(r) {
                const emps = r.message || [];
                self.$employee = self.$root.find("#fv-employee");
                self.$employee.empty().append('<option value="">Select Employee</option>');
                emps.forEach(e => self.$employee.append(`<option value="${e.name}">${e.employee_name || e.name}</option>`));
            }
        });
    }

    capture_location() {
        const self = this;
        const $status = this.$root.find("#fv-location-status");
        if (!navigator.geolocation) {
            $status.text("Geolocation not supported by this browser.").css("color", "#dc2626");
            return;
        }
        $status.html('<i class="fa fa-spinner fa-spin"></i> Capturing location...').css("color", "#374151");
        navigator.geolocation.getCurrentPosition(
            function(pos) {
                const lat = pos.coords.latitude;
                const lng = pos.coords.longitude;
                const acc = pos.coords.accuracy;
                self.$root.find("#fv-lat").val(lat);
                self.$root.find("#fv-lng").val(lng);
                self.$root.find("#fv-geolocation").val(JSON.stringify({type: "Feature", geometry: {type: "Point", coordinates: [lng, lat]}, properties: {accuracy: acc}}));
                $status.html(`<i class="fa fa-check-circle" style="color:#059669;"></i> Location captured: ${lat.toFixed(6)}, ${lng.toFixed(6)} (±${Math.round(acc)}m)`).css("color", "#059669");
                self.$root.find("#fv-map").show();
                // Load leaflet map
                if (typeof L !== "undefined") {
                    self.render_map(lat, lng);
                } else {
                    frappe.require("leaflet.bundle.js", function() {
                        frappe.require("leaflet.bundle.css", function() {
                            self.render_map(lat, lng);
                        });
                    });
                }
            },
            function(err) {
                $status.text("Location error: " + err.message).css("color", "#dc2626");
            },
            { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
        );
    }

    render_map(lat, lng) {
        const mapEl = this.$root.find("#fv-map")[0];
        if (!mapEl) return;
        if (this._map) { this._map.remove(); }
        this._map = L.map(mapEl).setView([lat, lng], 16);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: '&copy; OpenStreetMap contributors',
            maxZoom: 19,
        }).addTo(this._map);
        L.marker([lat, lng]).addTo(this._map).bindPopup("Visit location").openPopup();
    }

    preview_photo(e) {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = function(ev) {
            $("#fv-photo-img").attr("src", ev.target.result).parent().show();
        };
        reader.readAsDataURL(file);
    }

    save(is_draft) {
        const self = this;
        const employee = this.$employee.val();
        if (!employee) { frappe.msgprint({ title: "Missing", indicator: "orange", message: "Select an employee." }); return; }

        const lat = this.$root.find("#fv-lat").val();
        const lng = this.$root.find("#fv-lng").val();
        if (!lat || !lng) { frappe.msgprint({ title: "Missing", indicator: "orange", message: "Capture location first." }); return; }

        const $status = this.$status_bar;
        $status.html('<span class="fe-status-saving"><i class="fa fa-spinner fa-spin"></i> Saving...</span>');

        // Upload photo first if selected
        const photoFile = this.$root.find("#fv-photo")[0].files[0];
        const doSave = function(photoUrl) {
            const data = {
                employee: employee,
                company: self.$company.val() || "",
                visit_date: self.$root.find("#fv-date").val(),
                visit_time: self.$root.find("#fv-time").val(),
                party_type: self.$party_type.val(),
                party: self.$party.attr("data-party") || "",
                party_name: self.$party.val() || "",
                visit_type: self.$root.find("#fv-visit-type").val(),
                geolocation: self.$root.find("#fv-geolocation").val(),
                latitude: parseFloat(lat),
                longitude: parseFloat(lng),
                photo: photoUrl || "",
                remarks: self.$root.find("#fv-remarks").val() || "",
                status: is_draft ? "Draft" : "Submitted",
            };
            frappe.call({
                method: "fast_entry_app.api.field_visit.create_field_visit",
                args: { data: JSON.stringify(data) },
                callback: function(r) {
                    if (r.message && r.message.name) {
                        frappe.show_alert({ message: __("Visit {0} saved", [r.message.name]), indicator: "green" });
                        $status.html(`<span class="fe-status-ok"><i class="fa fa-check"></i> Saved: ${r.message.name}</span>`);
                        self.load_recent_visits();
                        // Reset form
                        self.$root.find("#fv-remarks").val("");
                        self.$root.find("#fv-photo").val("");
                        self.$root.find("#fv-photo-preview").hide();
                    } else {
                        $status.html('<span class="fe-status-error"><i class="fa fa-times"></i> Failed to save visit</span>');
                    }
                },
                error: function() {
                    $status.html('<span class="fe-status-error"><i class="fa fa-times"></i> Failed to save visit</span>');
                }
            });
        };

        if (photoFile) {
            const reader = new FileReader();
            reader.onload = function(ev) {
                frappe.call({
                    method: "frappe.client.insert",
                    args: {
                        doc: JSON.stringify({
                            doctype: "File",
                            file_name: photoFile.name,
                            folder: "Home",
                            is_private: 0,
                            content: ev.target.result.split(",")[1],
                            decode: 1,
                        }),
                    },
                    callback: function(r) {
                        if (r.message && r.message.file_url) {
                            doSave(r.message.file_url);
                        } else {
                            frappe.msgprint({ title: "Upload Failed", indicator: "red", message: "Photo upload failed." });
                            $status.html('<span class="fe-status-error"><i class="fa fa-times"></i> Photo upload failed</span>');
                        }
                    },
                    error: function() {
                        frappe.msgprint({ title: "Upload Failed", indicator: "red", message: "Photo upload failed." });
                        $status.html('<span class="fe-status-error"><i class="fa fa-times"></i> Photo upload failed</span>');
                    }
                });
            };
            reader.readAsDataURL(photoFile);
        } else {
            doSave("");
        }
    }

    load_recent_visits() {
        const self = this;
        frappe.call({
            method: "fast_entry_app.api.field_visit.get_field_visits",
            args: { limit: 20 },
            callback: function(r) {
                const visits = r.message || [];
                let html = "";
                if (!visits.length) {
                    html = '<div style="text-align:center;padding:20px;color:#9ca3af;">No visits logged yet.</div>';
                } else {
                    visits.forEach(function(v) {
                        const photo_html = v.photo ? `<img src="${v.photo}" style="width:60px;height:60px;object-fit:cover;border-radius:4px;margin-right:8px;" />` : "";
                        html += `<div style="display:flex;align-items:flex-start;padding:8px;border-bottom:1px solid #f3f4f6;gap:8px;">
                            ${photo_html}
                            <div style="flex:1;">
                                <div style="font-weight:600;font-size:13px;">${self.esc(v.employee_name || v.employee)} &mdash; ${self.esc(v.visit_type)}</div>
                                <div style="font-size:11px;color:#6b7280;">${v.visit_date || ""} ${v.visit_time || ""} ${v.party_name ? "&middot; " + self.esc(v.party_name) : ""}</div>
                                ${v.remarks ? `<div style="font-size:12px;color:#374151;margin-top:2px;">${self.esc(v.remarks)}</div>` : ""}
                                ${v.latitude ? `<div style="font-size:10px;color:#9ca3af;margin-top:2px;"><i class="fa fa-map-marker"></i> ${v.latitude}, ${v.longitude}</div>` : ""}
                            </div>
                            <span style="font-size:10px;padding:2px 6px;border-radius:4px;background:${v.status === 'Submitted' ? '#dcfce7' : '#fef9c3'};color:${v.status === 'Submitted' ? '#166534' : '#854d0e'};">${v.status}</span>
                        </div>`;
                    });
                }
                self.$root.find("#fv-recent-list").html(html);
            }
        });
    }
};