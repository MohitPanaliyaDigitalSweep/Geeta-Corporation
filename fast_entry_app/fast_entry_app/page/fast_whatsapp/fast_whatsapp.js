frappe.provide("fast_entry_app");

frappe.pages["fast-whatsapp"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({ parent: wrapper, title: __("WhatsApp Send"), single_column: true });
	frappe.breadcrumbs.add({
		type: "Custom",
		label: __("WhatsApp Send"),
		route: "fast-whatsapp",
	});
	new fast_entry_app.WhatsAppSend({ container: wrapper });
};

fast_entry_app.WhatsAppSend = class WhatsAppSend {
	constructor({ container }) {
		this.$container = $(container);
		this.doctype = "Sales Invoice";
		this.company = "All";
		this.sending = {};
		this.connected = false;
		this.poll = null;

		this.render();
		this.load_status();
		this.load_connection();
		this.load_invoices();
	}

	render() {
		this.$container.html(`
			<div class="wa-wrap" style="padding: 0 12px 12px;">
				<div id="wa-conn"></div>
				<div id="wa-status" class="wa-status"></div>

				<div class="wa-card">
					<div class="wa-card-head">
						<div class="wa-card-title"><i class="fa fa-send"></i> Send Document on WhatsApp</div>
					</div>
				<div class="wa-filters">
					<div class="wa-filter">
						<label>${__("Document Type")}</label>
						<select class="form-control input-sm" id="wa-doctype">
							<option value="Sales Invoice">${__("Sales Invoice")}</option>
							<option value="Purchase Invoice">${__("Purchase Invoice")}</option>
							<option value="Quotation">${__("Quotation")}</option>
						</select>
					</div>
					<div class="wa-filter">
						<label>${__("Company")}</label>
						<select class="form-control input-sm" id="wa-company"></select>
					</div>
					<div class="wa-filter wa-filter-btn">
						<button class="btn btn-primary btn-sm" id="wa-refresh">
							<i class="fa fa-refresh"></i> ${__("Refresh")}
						</button>
					</div>
				</div>
					<div id="wa-table-wrap" class="wa-table-wrap"></div>
				</div>
			</div>
		`);

		this.setup_filters();
		this.bind_events();
		this.inject_styles();
	}

	inject_styles() {
		if (document.getElementById("wa-page-styles")) return;
		$("head").append(`
			<style id="wa-page-styles">
				.wa-wrap { max-width: 1400px; margin: 0 auto; }
				.wa-status { margin: 10px 0 4px; }
				.wa-card { border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; margin-top: 10px; }
				.wa-card-head { padding: 12px 14px; border-bottom: 1px solid var(--border-color); background: var(--gray-50); }
				.wa-card-title { font-weight: 600; font-size: 14px; }
				.wa-filters { display: flex; flex-wrap: wrap; gap: 14px; padding: 12px 14px; border-bottom: 1px solid var(--border-color); align-items: flex-end; }
				.wa-filter { display: flex; flex-direction: column; min-width: 200px; }
				.wa-filter-btn { min-width: 0; padding-bottom: 1px; }
				.wa-table-wrap { max-height: 68vh; overflow: auto; }
				.wa-table { width: 100%; border-collapse: collapse; font-size: 13px; }
				.wa-table th { position: sticky; top: 0; z-index: 2; background: var(--gray-50);
					text-align: left; padding: 9px 12px; border-bottom: 1px solid var(--border-color);
					font-weight: 600; color: var(--text-color); white-space: nowrap; }
				.wa-table td { padding: 9px 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
				.wa-table tr:hover td { background: var(--gray-50); }
				.wa-num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
				.wa-chip { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }
				.wa-chip-ok { background: var(--green-100); color: var(--green-600); }
				.wa-chip-no { background: var(--orange-100); color: var(--orange-600); }
				.wa-chip-bad { background: var(--red-100); color: var(--red-600); }
				.wa-sub { font-size: 10px; color: var(--text-muted); margin: 2px 0 3px; }
				.wa-setnum { margin-top: 2px; }
				.wa-banner { padding: 11px 14px; border-radius: 6px; font-size: 13px; display: flex; gap: 8px; align-items: flex-start; }
				.wa-banner-ok { background: var(--green-100); color: var(--green-700); }
				.wa-banner-warn { background: var(--orange-100); color: var(--orange-700); }
				.wa-banner-err { background: var(--red-100); color: var(--red-600); }
				.wa-empty { padding: 34px 14px; text-align: center; color: var(--text-muted); }
				.wa-mono { font-family: var(--font-stack-monospace, monospace); font-size: 12px; }
				/* connection card */
				.wa-conn-card { border: 1px solid var(--border-color); border-radius: 8px; margin-top: 10px; overflow: hidden; }
				.wa-conn-head { display: flex; align-items: center; gap: 10px; padding: 12px 14px;
					border-bottom: 1px solid var(--border-color); background: var(--gray-50); }
				.wa-conn-title { font-weight: 600; font-size: 14px; flex: 1; }
				.wa-pill { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px;
					border-radius: 12px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .3px; }
				.wa-pill-ok { background: var(--green-100); color: var(--green-700); }
				.wa-pill-warn { background: var(--orange-100); color: var(--orange-700); }
				.wa-pill-err { background: var(--red-100); color: var(--red-700); }
				.wa-pill .dot { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
				.wa-conn-body { padding: 14px; display: flex; gap: 20px; flex-wrap: wrap; align-items: flex-start; }
				.wa-qr-box { text-align: center; }
				.wa-qr-box img { width: 208px; height: 208px; border: 1px solid var(--border-color);
					border-radius: 6px; background: #fff; padding: 6px; }
				.wa-qr-caption { font-size: 12px; color: var(--text-muted); margin-top: 7px; max-width: 210px; }
				.wa-qr-spin { width: 208px; height: 208px; display: flex; align-items: center; justify-content: center;
					border: 1px dashed var(--border-color); border-radius: 6px; color: var(--text-muted); font-size: 12px; }
				.wa-conn-info { flex: 1; min-width: 260px; }
				.wa-kv { display: flex; gap: 8px; font-size: 13px; padding: 4px 0; }
				.wa-kv .k { color: var(--text-muted); min-width: 108px; }
				.wa-kv .v { font-weight: 500; word-break: break-all; }
				.wa-conn-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
				.wa-steps { margin: 6px 0 0; padding-left: 18px; font-size: 12px; color: var(--text-muted); line-height: 1.7; }
				.wa-code { font-size: 26px; font-weight: 700; letter-spacing: 4px; font-family: var(--font-stack-monospace, monospace);
					padding: 10px 0; color: var(--text-color); }
				/* health report */
				.wa-health { margin-top: 10px; }
				.wa-health-row { display: flex; gap: 10px; align-items: flex-start; padding: 8px 12px;
					border-bottom: 1px solid var(--border-color); font-size: 13px; }
				.wa-health-row:last-child { border-bottom: 0; }
				.wa-health-ico { width: 16px; text-align: center; flex: 0 0 16px; }
				.wa-health-ico.ok { color: var(--green-600); }
				.wa-health-ico.warn { color: var(--orange-600); }
				.wa-health-ico.error { color: var(--red-600); }
				.wa-health-name { font-weight: 600; min-width: 160px; }
				.wa-health-msg { color: var(--text-muted); flex: 1; }
				.wa-health-ms { color: var(--text-muted); font-size: 11px; }
			</style>
		`);
	}

	setup_filters() {
		const self = this;

		this.$container
			.find("#wa-doctype")
			.val(this.doctype)
			.on("change", function () {
				self.doctype = $(this).val();
				self.load_invoices();
			});

		frappe.call({
			method: "fast_entry_app.fast_entry_app.page.fast_whatsapp.fast_whatsapp.get_company_options",
			callback: (r) => {
				const companies = (r.message && r.message.companies) || [];
				const $sel = self.$container.find("#wa-company");
				$sel.html(
					$("<option>")
						.attr("value", "All")
						.text(__("All Companies"))
						.prop("outerHTML") +
						companies
							.map((c) => $("<option>").attr("value", c).text(c).prop("outerHTML"))
							.join("")
				);
				$sel.val("All").on("change", function () {
					self.company = $(this).val() || "All";
					self.load_invoices();
				});
			},
		});
	}

	bind_events() {
		const self = this;
		this.$container.find("#wa-refresh").on("click", () => {
			self.load_status();
			self.load_connection();
			self.load_invoices();
		});
	}

	// ------------------------------------------------------------------
	// Connection card: live session state, QR pairing, health check
	// ------------------------------------------------------------------

	wa_call(method, args, callback) {
		frappe.call({
			method: "fast_entry_app.api." + method,
			args: args || {},
			callback: (r) => callback(r.message || {}),
			error: (e) => callback({ ok: false, message: (e && e.message) || __("Request failed") }),
		});
	}

	load_connection() {
		this.wa_call("wa_session.get_session_status", {}, (s) => {
			const was_connected = this.connected;
			this.connected = !!s.connected;
			this.render_connection(s);

			// Auto-refresh the QR while waiting to be paired; stop polling once linked.
			if (this.connected) {
				this.stop_poll();
				if (!was_connected) {
					frappe.show_alert({ message: __("WhatsApp number linked"), indicator: "green" });
					this.load_invoices();
				}
			} else {
				this.start_poll();
			}
		});
	}

	start_poll() {
		if (this.poll) return;
		this.poll = setInterval(() => this.load_connection(), 5000);
	}

	stop_poll() {
		if (this.poll) {
			clearInterval(this.poll);
			this.poll = null;
		}
	}

	load_qr() {
		// Only the QR slot is replaced - the info column and its buttons must survive.
		const $slot = this.$container.find("#wa-qr-slot");
		$slot.html(`<div class="wa-qr-spin"><span><i class="fa fa-spinner fa-spin"></i> ${__(
			"Generating QR…"
		)}</span></div>`);
		this.wa_call("wa_session.get_session_qr", {}, (r) => {
			if (r.ok && r.qr) {
				$slot.html(`
					<img src="${r.qr}" alt="${__("WhatsApp pairing QR")}" id="wa-qr-img">
					<div class="wa-qr-caption">${__(
						"Open WhatsApp on the phone you want to link: Settings → Linked devices → Link a device, then scan. The QR refreshes automatically."
					)}</div>`);
			} else {
				$slot.html(`<div class="wa-qr-spin" style="flex-direction:column;gap:8px">
					<span>${frappe.utils.escape_html(r.message || __("No QR available"))}</span>
					<button class="btn btn-sm btn-primary" id="wa-qr-retry">${__("Retry")}</button>
				</div>`);
				$slot.find("#wa-qr-retry").on("click", () => this.load_qr());
			}
		});
	}

	render_connection(s) {
		const $el = this.$container.find("#wa-conn");
		if (s.configured === false) {
			$el.html(`<div class="wa-conn-card"><div class="wa-conn-head">
				<div class="wa-conn-title"><i class="fa fa-link"></i> WhatsApp Connection</div>
				<span class="wa-pill wa-pill-err"><span class="dot"></span>${__("Not configured")}</span>
				</div><div class="wa-conn-body"><div class="wa-conn-info">
				<div class="wa-kv"><span class="k">${__("Reason")}</span><span class="v">${frappe.utils.escape_html(
					s.message || ""
				)}</span></div>
				<div class="wa-conn-actions"><a class="btn btn-sm btn-primary" href="/app/fast-entry-settings">${__(
					"Open Fast Entry Settings"
				)}</a></div>
				</div></div></div>`);
			return;
		}

		if (s.ok === false) {
			$el.html(`<div class="wa-conn-card"><div class="wa-conn-head">
				<div class="wa-conn-title"><i class="fa fa-link"></i> WhatsApp Connection</div>
				<span class="wa-pill wa-pill-err"><span class="dot"></span>${__("Unreachable")}</span>
				</div><div class="wa-conn-body"><div class="wa-conn-info">
				<div class="wa-kv"><span class="k">${__("Gateway")}</span><span class="v">${frappe.utils.escape_html(
					s.base_url || ""
				)}</span></div>
				<div class="wa-kv"><span class="k">${__("Error")}</span><span class="v">${frappe.utils.escape_html(
					s.message || ""
				)}</span></div>
				<div class="wa-conn-actions">
					<button class="btn btn-sm btn-primary" id="wa-start">${__("Start session")}</button>
					<button class="btn btn-sm btn-default" id="wa-check">${__("Check server")}</button>
				</div>
				</div></div></div>`);			this.bind_conn_events();
			return;
		}

		const pill = s.connected
			? `<span class="wa-pill wa-pill-ok"><span class="dot"></span>${__("Connected")}</span>`
			: `<span class="wa-pill wa-pill-warn"><span class="dot"></span>${frappe.utils.escape_html(
					s.status || __("Not linked")
			  )}</span>`;

		const left = s.connected
			? `<div class="wa-qr-spin" style="flex-direction:column;gap:6px">
					<i class="fa fa-check-circle" style="font-size:30px;color:var(--green-600)"></i>
					<span>${__("Ready to send")}</span></div>`
			: `<div class="wa-qr-spin"><span><i class="fa fa-spinner fa-spin"></i> ${__(
					"Preparing QR…"
			  )}</span></div>`;

		$el.html(`
			<div class="wa-conn-card">
				<div class="wa-conn-head">
					<div class="wa-conn-title"><i class="fa fa-link"></i> WhatsApp Connection</div>
					${pill}
					<button class="btn btn-sm btn-default" id="wa-check"><i class="fa fa-heartbeat"></i> ${__(
				"Check server"
			)}</button>
				</div>
				<div class="wa-conn-body" id="wa-conn-body">
					<div class="wa-qr-box" id="wa-qr-slot">${left}</div>
					<div class="wa-conn-info">
						<div class="wa-kv"><span class="k">${__("Gateway")}</span><span class="v wa-mono">${frappe.utils.escape_html(
							s.base_url || ""
						)}</span></div>
						<div class="wa-kv"><span class="k">${__("Session")}</span><span class="v">${frappe.utils.escape_html(
							s.name || s.session_id || ""
						)} <span class="wa-mono">(${frappe.utils.escape_html(s.status || "")})</span></span></div>
						<div class="wa-kv"><span class="k">${__("Linked number")}</span><span class="v">${
							s.connected
								? `<span class="wa-chip wa-chip-ok">+${frappe.utils.escape_html(s.phone || "")}</span>`
								: `<span class="wa-chip wa-chip-no">${__("None")}</span>`
						}</span></div>
						${
							s.last_error
								? `<div class="wa-kv"><span class="k">${__("Last error")}</span><span class="v">${frappe.utils.escape_html(
										s.last_error
									)}</span></div>`
								: ""
						}
						${
							s.restriction
								? `<div class="wa-kv"><span class="k">${__("Restriction")}</span><span class="v" style="color:var(--red-600)">${frappe.utils.escape_html(
										s.restriction
									)}</span></div>`
								: ""
						}
						<div class="wa-conn-actions">
							${
								s.connected
									? `<button class="btn btn-sm btn-default" id="wa-unlink">${__("Unlink device")}</button>`
									: `<button class="btn btn-sm btn-primary" id="wa-qr">${__("Show QR to link")}</button>
									   <button class="btn btn-sm btn-default" id="wa-phone">${__(
												"Link with phone number"
										  )}</button>`
							}
							${
								s.engine_loaded
									? ""
									: `<button class="btn btn-sm btn-primary" id="wa-start">${__("Start session")}</button>`
							}
						</div>
					</div>
				</div>
			</div>
			<div id="wa-health"></div>`);

		this.bind_conn_events();
		if (!s.connected) this.load_qr();
	}

	bind_conn_events() {
		const self = this;
		const $c = this.$container.find("#wa-conn");

		$c.find("#wa-qr").on("click", () => self.load_qr());

		$c.find("#wa-start").on("click", function () {
			const $btn = $(this).prop("disabled", true);
			self.wa_call("wa_session.start_session", {}, (r) => {
				$btn.prop("disabled", false);
				frappe.show_alert({
					message: r.ok ? __("Session starting…") : r.message || __("Could not start session"),
					indicator: r.ok ? "green" : "red",
				});
				setTimeout(() => self.load_connection(), 2500);
			});
		});

		$c.find("#wa-unlink").on("click", function () {
			frappe.confirm(
				__("Unlink this device from WhatsApp? You will need to scan a new QR to send again."),
				() => {
					const $btn = $(this).prop("disabled", true);
					self.wa_call("wa_session.logout_session", {}, (r) => {
						$btn.prop("disabled", false);
						frappe.show_alert({
							message: r.ok ? r.message : r.message || __("Unlink failed"),
							indicator: r.ok ? "green" : "red",
						});
						setTimeout(() => self.load_connection(), 2500);
					});
				}
			);
		});

		$c.find("#wa-phone").on("click", () => self.show_pairing_dialog());

		$c.find("#wa-check").on("click", () => self.run_health_check());
	}

	show_pairing_dialog() {
		const self = this;
		const d = new frappe.ui.Dialog({
			title: __("Link with phone number"),
			fields: [
				{
					fieldname: "phone",
					fieldtype: "Data",
					label: __("Phone number (with country code)"),
					description: __("Digits only, international format - e.g. 919876543210"),
					reqd: 1,
				},
			],
			primary_action_label: __("Get pairing code"),
			primary_action: (values) => {
				d.disable_primary_action();
				self.wa_call("wa_session.request_pairing_code", { phone_number: values.phone }, (r) => {
					d.enable_primary_action();
					if (!r.ok) {
						frappe.msgprint({ title: __("Pairing code failed"), message: r.message, indicator: "red" });
						return;
					}
					d.clear();
					frappe.msgprint({
						title: __("Pairing code"),
						message: `<div style="text-align:center">
							<div class="wa-code">${frappe.utils.escape_html(r.pairing_code || "")}</div>
							<div style="font-size:12px">${__(
								"In WhatsApp: Settings → Linked devices → Link with phone number, then enter this code."
							)}</div></div>`,
						indicator: "green",
					});
					self.start_poll();
				});
			},
		});
		d.show();
	}

	run_health_check() {
		const self = this;
		const $h = this.$container.find("#wa-health");
		$h.html(`<div class="wa-conn-card"><div class="wa-conn-body">
			<span><i class="fa fa-spinner fa-spin"></i> ${__("Checking gateway…")}</span></div></div>`);

		this.wa_call("wa_health.check_gateway", {}, (r) => {
			const ico = { ok: "check-circle", warn: "exclamation-triangle", error: "times-circle" };
			const rows = (r.checks || [])
				.map(
					(c) => `<div class="wa-health-row">
						<span class="wa-health-ico ${c.level}"><i class="fa fa-${ico[c.level] || "circle"}"></i></span>
						<span class="wa-health-name">${frappe.utils.escape_html(c.name)}</span>
						<span class="wa-health-msg">${frappe.utils.escape_html(c.message)}</span>
						<span class="wa-health-ms">${c.ms ? c.ms + "ms" : ""}</span>
					</div>`
				)
				.join("");

			$h.html(`
				<div class="wa-conn-card">
					<div class="wa-conn-head">
						<div class="wa-conn-title"><i class="fa fa-heartbeat"></i> ${__("Server health check")}</div>
						<span class="wa-pill ${
							r.ok ? "wa-pill-ok" : "wa-pill-err"
						}"><span class="dot"></span>${r.ok ? __("Healthy") : __("Needs attention")}</span>
						<button class="btn btn-sm btn-default" id="wa-check2">${__("Re-check")}</button>
					</div>
					<div class="wa-health">${rows}</div>
				</div>`);
			$h.find("#wa-check2").on("click", () => self.run_health_check());
		});
	}

	load_status() {
		const self = this;
		frappe.call({
			method: "fast_entry_app.fast_entry_app.page.fast_whatsapp.fast_whatsapp.get_whatsapp_status",
			callback: (r) => {
				const s = r.message || {};
				const $el = self.$container.find("#wa-status");
				if (!s.enabled) {
					$el.html(
						`<div class="wa-banner wa-banner-warn"><i class="fa fa-exclamation-triangle"></i>
						 <div>${__("WhatsApp sending is disabled.")} ${__("Enable it in")} <a href="/app/fast-entry-settings">${__("Fast Entry Settings")}</a>.</div></div>`
					);
				} else if (!s.has_api_key || !s.session_id) {
					$el.html(
						`<div class="wa-banner wa-banner-err"><i class="fa fa-times-circle"></i>
						 <div>${__("WhatsApp sending is enabled but incomplete.")} ${__("Set the OpenWA API key and session ID in")} <a href="/app/fast-entry-settings">${__("Fast Entry Settings")}</a>.</div></div>`
					);
				} else {
					$el.html(
						`<div class="wa-banner wa-banner-ok"><i class="fa fa-check-circle"></i>
						 <div>${__("WhatsApp sending is configured.")} <span class="wa-mono">${frappe.utils.escape_html(
							s.base_url || ""
						)}</span> &middot; ${__("Session")} <span class="wa-mono">${frappe.utils.escape_html(
							(s.session_id || "").slice(0, 8)
						)}…</span>${s.print_format ? " &middot; " + __("Format") + ": " + frappe.utils.escape_html(s.print_format) : ""}</div></div>`
					);
				}
			},
			error: () => {
				self.$container
					.find("#wa-status")
					.html(`<div class="wa-banner wa-banner-err"><i class="fa fa-times-circle"></i><div>${__("Could not read WhatsApp settings.")}</div></div>`);
			},
		});
	}

	load_invoices() {
		const self = this;
		const $wrap = this.$container.find("#wa-table-wrap");
		$wrap.html(`<div class="wa-empty"><i class="fa fa-spinner fa-spin"></i> ${__("Loading…")}</div>`);

		frappe.call({
			method: "fast_entry_app.fast_entry_app.page.fast_whatsapp.fast_whatsapp.get_sendable_invoices",
			args: { doctype: this.doctype, company: this.company, limit: 50 },
			callback: (r) => {
				const rows = (r.message && r.message.invoices) || [];
				self.render_table(rows);
			},
			error: (e) => {
				$wrap.html(`<div class="wa-empty">${frappe.utils.escape_html(e.message || __("Failed to load documents."))}</div>`);
			},
		});
	}

	render_table(rows) {
		const self = this;
		const $wrap = this.$container.find("#wa-table-wrap");

		// Keep rows addressable so the row actions (Add/Edit number) can reach them.
		this.rows_by_name = {};
		rows.forEach((r) => {
			this.rows_by_name[r.name] = r;
		});

		if (!rows.length) {
			$wrap.html(
				`<div class="wa-empty"><i class="fa fa-inbox"></i><br>${__("No submitted documents found.")}</div>`
			);
			return;
		}

		let html = `<table class="wa-table">
			<thead><tr>
				<th>${__("Document")}</th>
				<th>${__("Party")}</th>
				<th>${__("Company")}</th>
				<th>${__("Date")}</th>
				<th class="wa-num">${__("Grand Total")}</th>
				<th>${__("Mobile")}</th>
				<th style="width:110px;">${__("Action")}</th>
			</tr></thead><tbody>`;

		rows.forEach((r) => {
			const fmt = self.format_currency(r.grand_total, r.currency);
			html += `<tr data-name="${frappe.utils.escape_html(r.name)}">
				<td><a href="/app/${frappe.utils.escape_html(
					r.doctype.toLowerCase().replace(/ /g, "-")
				)}/${frappe.utils.escape_html(r.name)}" target="_blank" rel="noopener">${frappe.utils.escape_html(r.name)}</a></td>
				<td>${frappe.utils.escape_html(r.party_display || r.party || "")}</td>
				<td>${frappe.utils.escape_html(r.company || "")}</td>
				<td>${frappe.utils.escape_html(r.doc_date || "")}</td>
				<td class="wa-num">${frappe.utils.escape_html(fmt)}</td>
				<td>${self.render_mobile_cell(r)}</td>
				<td><button class="btn btn-sm btn-primary wa-send" data-name="${frappe.utils.escape_html(
				r.name
			)}" data-doctype="${frappe.utils.escape_html(r.doctype)}" data-mobile="${frappe.utils.escape_html(
				r.mobile || ""
			)}" ${r.has_mobile ? "" : "disabled"}>${__("Send")}</button></td>
			</tr>`;
		});

		html += `</tbody></table>`;
		$wrap.html(html);

		$wrap.find(".wa-send").on("click", function () {
			const $btn = $(this);
			self.send_one($btn.data("doctype"), $btn.data("name"), $btn);
		});
		$wrap.find(".wa-setnum").on("click", function () {
			const $btn = $(this);
			self.show_number_dialog(self.rows_by_name[$btn.data("name")]);
		});
	}

	/**
	 * Format a currency for a table cell.
	 *
	 * frappe.format() with fieldtype "Currency" returns a full HTML wrapper
	 * (`<div style='text-align: right'>₹ 3,449.84</div>`). Escaping that would print the
	 * markup as visible text, so unwrap it and keep the plain text; the .wa-num class
	 * already handles right alignment.
	 */
	format_currency(value, currency) {
		if (value === null || value === undefined || value === "") return "";
		const formatted = frappe.format(value, {
			fieldtype: "Currency",
			options: "currency",
			currency: currency,
			precision: 2,
		});
		if (!formatted) return "";

		const holder = document.createElement("div");
		holder.innerHTML = formatted;
		// Non-breaking spaces are used for grouping; normalise so the text stays selectable.
		return holder.textContent.replace(/\u00a0/g, " ").trim();
	}

	/** Mobile cell: resolved number + its source, or a prompt to add/choose one. */
	render_mobile_cell(r) {
		const esc = frappe.utils.escape_html;
		if (r.stored_mobile_invalid) {
			return `<span class="wa-chip wa-chip-bad" title="${esc(r.stored_mobile)}">${__(
				"Invalid number"
			)}</span>
				<div class="wa-sub">${esc(r.stored_mobile)}</div>
				<button class="btn btn-xs btn-default wa-setnum" data-name="${esc(r.name)}">${__("Fix")}</button>`;
		}
		if (r.has_mobile) {
			const more = (r.candidates || []).length > 1;
			return `<span class="wa-chip wa-chip-ok">${esc(r.mobile)}</span>
				<div class="wa-sub">${esc(r.mobile_source || "")}</div>
				${
					more
						? `<button class="btn btn-xs btn-default wa-setnum" data-name="${esc(
								r.name
						  )}">${__("Change")} (${r.candidates.length})</button>`
						: `<button class="btn btn-xs btn-default wa-setnum" data-name="${esc(r.name)}">${__(
								"Edit"
						  )}</button>`
				}`;
		}
		return `<span class="wa-chip wa-chip-no">${__("Missing")}</span>
			<button class="btn btn-xs btn-primary wa-setnum" data-name="${esc(r.name)}">${__("Add number")}</button>`;
	}

	/** Dialog to add a missing number, fix an invalid one, or choose a different default. */
	show_number_dialog(r) {
		if (!r) return;
		const self = this;
		const esc = frappe.utils.escape_html;
		const candidates = r.candidates || [];
		const targets = r.save_targets || [{ value: "document", label: __("This document") }];

		const cands_field = candidates.length
			? {
					fieldname: "candidate",
					fieldtype: "Select",
					label: __("Choose a number"),
					options: [
						"",
						...candidates.map((c) => `${esc(c.value)} — ${esc(c.source)}`),
						__("Enter a different number…"),
					],
			  }
			: null;

		// Frappe.Dialog cannot handle a null entry in `fields`, so build it conditionally.
		const fields = [
			{
				fieldname: "headline",
				fieldtype: "HTML",
				options: `<div style="font-size:12px;color:var(--text-muted);margin-bottom:6px">
					${esc(r.name)} · ${esc(r.party_display || "")}</div>`,
			},
		];
		if (cands_field) fields.push(cands_field);
		fields.push({
			fieldname: "mobile",
			fieldtype: "Data",
			label: __("Mobile number"),
			description: __("Any format works: +91-9327802242, 09327802242 or 9327802242"),
			reqd: 1,
			default: candidates.length ? candidates[0].value : (r.stored_mobile || ""),
		});
		fields.push({
			fieldname: "target",
			fieldtype: "Select",
			label: __("Save to"),
			options: targets.map((t) => t.label),
			default: targets[0].label,
		});

		const d = new frappe.ui.Dialog({
			title: candidates.length ? __("Choose WhatsApp number") : __("Add WhatsApp number"),
			fields: fields,
			primary_action_label: __("Save number"),
			primary_action: (values) => {
				const target = (targets.find((t) => t.label === values.target) || targets[0]).value;
				d.disable_primary_action();
				frappe.call({
					method: "fast_entry_app.api.invoice_send.set_whatsapp_number",
					args: {
						doctype: r.doctype,
						name: r.name,
						mobile: values.mobile,
						target: target,
					},
					callback: (resp) => {
						d.enable_primary_action();
						const m = resp.message || {};
						if (m.ok) {
							frappe.show_alert({
								message: `${__("Number saved")} → ${m.saved_on} · ${m.chat_id}`,
								indicator: "green",
							});
							d.hide();
							self.load_invoices();
						}
					},
					error: (e) => {
						d.enable_primary_action();
						frappe.msgprint({
							title: __("Could not save number"),
							message: (e && e.message) || __("Unknown error"),
							indicator: "red",
						});
					},
				});
			},
		});

		if (cands_field) {
			d.fields_dict.candidate.$input.on("change", function () {
				const val = $(this).val();
				if (!val) return;
				if (val === __("Enter a different number…")) {
					d.set_value("mobile", "");
					return;
				}
				// Map the visible "number — source" label back to the raw stored value.
				const idx = candidates.findIndex((c) => `${esc(c.value)} — ${esc(c.source)}` === val);
				if (idx > -1) d.set_value("mobile", candidates[idx].value);
			});
		}
		d.show();
	}

	send_one(doctype, name, $btn) {
		const self = this;
		const key = doctype + "|" + name;
		if (this.sending[key]) return;

		this.sending[key] = true;
		const original = $btn.html();
		$btn.prop("disabled", true).html(`<i class="fa fa-spinner fa-spin"></i> ${__("Sending…")}`);

		const method_map = {
			"Sales Invoice": "send_invoice_whatsapp",
			"Purchase Invoice": "send_purchase_invoice_whatsapp",
			"Quotation": "send_quotation_whatsapp",
		};
		const arg_map = {
			"Sales Invoice": "invoice_name",
			"Purchase Invoice": "purchase_invoice_name",
			"Quotation": "quotation_name",
		};

		const args = {};
		args[arg_map[doctype]] = name;

		frappe.call({
			method: "fast_entry_app.api.invoice_send." + method_map[doctype],
			args: args,
			freeze: true,
			callback: (r) => {
				const m = r.message || {};
				if (m.ok) {
					frappe.show_alert({
						message: __("Sent {0} to {1} (msg {2})", [
							name,
							m.chat_id || "",
							m.message_id || "—",
						]),
						indicator: "green",
					});
				} else if (m.not_configured) {
					frappe.msgprint({
						title: __("WhatsApp Not Configured"),
						message: m.message || "",
						indicator: "orange",
					});
				} else if (m.missing_field) {
					frappe.msgprint({
						title: __("Mobile Number Missing"),
						message: m.message || "",
						indicator: "orange",
					});
					self.load_invoices();
				} else {
					frappe.msgprint({
						title: __("WhatsApp Send Failed"),
						message: m.message || __("Unknown error"),
						indicator: "red",
					});
				}
			},
			error: (e) => {
				frappe.msgprint({
					title: __("WhatsApp Send Failed"),
					message: (e && e.message) || __("Unknown error"),
					indicator: "red",
				});
			},
			always: () => {
				delete self.sending[key];
				$btn.prop("disabled", false).html(original);
			},
		});
	}
};
