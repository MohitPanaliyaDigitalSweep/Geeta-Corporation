frappe.provide("fast_entry_app");

frappe.pages["fast-master-data"].on_page_load = function (wrapper) {
	frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Load Master Data"),
		single_column: true,
	});
	frappe.breadcrumbs.add({
		type: "Custom",
		label: __("Load Master Data"),
		route: "fast-master-data",
	});
	new fast_entry_app.MasterDataLoader({ container: wrapper });
};

fast_entry_app.MasterDataLoader = class MasterDataLoader {
	constructor({ container }) {
		this.$container = $(container);
		this.overview = null;
		this.running = false;
		if (typeof window !== "undefined") window.__MDL = this;

		this.render();
		this.inject_styles();
		this.load_overview();
	}

	inject_styles() {
		if (document.getElementById("md-page-styles")) return;
		$("head").append(`
			<style id="md-page-styles">
				.md-wrap { max-width: 1100px; margin: 0 auto; }
				.md-card { border: 1px solid var(--border-color); border-radius: 8px; overflow: hidden; margin-top: 12px; }
				.md-card-head { padding: 10px 14px; border-bottom: 1px solid var(--border-color); background: var(--gray-50); font-weight: 600; font-size: 13px; }
				.md-card-body { padding: 12px 14px; font-size: 13px; }
				.md-phase { padding: 8px 0; border-bottom: 1px dashed var(--border-color); }
				.md-phase:last-child { border-bottom: none; }
				.md-phase label { display: flex; align-items: center; gap: 8px; cursor: pointer; }
				.md-phase-detail { margin: 4px 0 2px 24px; color: var(--text-muted); }
				.md-phase-doctypes { margin-left: 24px; font-size: 12px; }
				.md-badge { background: var(--gray-200); border-radius: 10px; padding: 1px 9px; font-size: 12px; font-weight: 600; }
				.md-exist { display: inline-block; margin: 0 14px 4px 0; }
				.md-actions { display: flex; align-items: center; gap: 10px; margin: 16px 0 4px; }
				.md-status { font-size: 13px; }
				.md-summary { display: flex; gap: 8px; flex-wrap: wrap; }
				.md-chip { border-radius: 10px; padding: 2px 11px; font-size: 12px; font-weight: 600; }
				.md-chip-ok { background: var(--green-100); color: var(--green-700); }
				.md-chip-skip { background: var(--gray-200); color: var(--gray-700); }
				.md-chip-bad { background: var(--red-100); color: var(--red-700); }
				.md-table { width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 8px; }
				.md-table th, .md-table td { border-bottom: 1px solid var(--border-color); padding: 5px 8px; text-align: left; vertical-align: top; }
				code { background: var(--gray-100); border-radius: 3px; padding: 1px 5px; word-break: break-all; }
			</style>
		`);
	}

	// ---------------------------------------------------------------- markup

	render() {
		this.$container.html(`
			<div class="md-wrap" style="padding: 0 12px 24px;">
				<div class="alert alert-warning" style="margin-bottom: 16px;">
					<i class="fa fa-exclamation-triangle"></i>
					${__("This loads master data into the current site. Read the plan before applying.")}
					${__("Nothing is ever deleted; existing records are skipped.")}
				</div>

				<div class="md-card">
					<div class="md-card-head"><i class="fa fa-file-code-o"></i> ${__("Bundle")}</div>
					<div class="md-card-body" id="md-bundle">${__("Loading...")}</div>
				</div>

				<div class="md-card">
					<div class="md-card-head"><i class="fa fa-list-ol"></i> ${__("Phases")}</div>
					<div class="md-card-body" id="md-phases">${__("Loading...")}</div>
				</div>

				<div class="md-card">
					<div class="md-card-head"><i class="fa fa-database"></i> ${__("Already on this site")}</div>
					<div class="md-card-body" id="md-existing">${__("Loading...")}</div>
				</div>

				<div class="md-actions">
					<button class="btn btn-sm btn-secondary" id="md-dry">
						<i class="fa fa-play"></i> ${__("Dry Run")}
					</button>
					<button class="btn btn-sm btn-primary" id="md-apply">
						<i class="fa fa-check"></i> ${__("Apply")}
					</button>
					<span id="md-status" class="md-status"></span>
				</div>

				<div class="md-card" id="md-result-card" style="display: none;">
					<div class="md-card-head"><i class="fa fa-list-alt"></i> ${__("Result")}</div>
					<div class="md-card-body" id="md-result"></div>
				</div>
			</div>
		`);

		this.$("#md-dry").on("click", () => this.run(false));
		this.$("#md-apply").on("click", () => this.run(true));
	}

	$(sel) {
		return this.$container.find(sel);
	}

	esc(value) {
		return frappe.utils.escape_html(value == null ? "" : String(value));
	}

	// --------------------------------------------------------------- loading

	load_overview() {
		frappe.call({
			method: "fast_entry_app.fast_entry_app.page.fast_master_data.fast_master_data.get_seed_overview",
			callback: (r) => {
				this.overview = r.message;
				this.render_overview();
			},
			error: () => this.$("#md-bundle").html(`<span class="text-muted">${__("Could not load bundle overview.")}</span>`),
		});
	}

	selected_phases() {
		return this.$("#md-phases input[type=checkbox]:checked")
			.map(function () {
				return $(this).val();
			})
			.get();
	}

	render_overview() {
		const o = this.overview;

		this.$("#md-bundle").html(`
			<div><strong>${__("File")}:</strong> <code>${this.esc(o.bundle_path)}</code></div>
			<div><strong>${__("Total documents")}:</strong> ${o.total_docs}</div>
			<div><strong>${__("Anonymised")}:</strong> ${o.anonymised ? __("Yes") : __("No")}</div>
			${o.generated_on ? `<div><strong>${__("Generated on")}:</strong> ${this.esc(o.generated_on)}</div>` : ""}
		`);

		this.$("#md-phases").html(
			(o.phases || [])
				.map(
					(p, i) => `
					<div class="md-phase">
						<label>
							<input type="checkbox" class="md-phase-cb" value="${this.esc(p.phase)}" data-i="${i}">
							<strong>${this.esc(p.phase)}</strong>
							<span class="md-badge">${p.docs}</span>
						</label>
						<div class="md-phase-detail">${this.esc(p.detail)}</div>
						<div class="md-phase-doctypes text-muted">${this.esc((p.doctypes || []).join(", "))}</div>
					</div>`
				)
				.join("") ||
				`<span class="text-muted">${__("No phases found in the bundle.")}</span>`
		);

		// Default: everything selected.
		this.$("#md-phases input[type=checkbox]").prop("checked", true);
		this.$("#md-phases input[type=checkbox]").on("change", () => this.render_status_hint());

		this.$("#md-existing").html(
			Object.entries(o.existing || {})
				.map(
					([dt, n]) =>
						`<span class="md-exist"><strong>${this.esc(dt)}</strong> ${n}</span>`
				)
				.join("") || `<span class="text-muted">${__("Nothing yet.")}</span>`
		);

		this.render_status_hint();
	}

	render_status_hint() {
		const n = this.selected_phases().length;
		this.$("#md-status").html(
			n
				? __("{0} phase(s) selected", [n])
				: `<span class="text-muted">${__("No phases selected")}</span>`
		);
	}

	// ---------------------------------------------------------------- running

	run(apply_changes) {
		if (this.running) return;

		const phases = this.selected_phases();
		if (!phases.length) {
			frappe.show_alert({ message: __("Select at least one phase."), indicator: "orange" });
			return;
		}

		if (apply_changes) {
			frappe.confirm(
				__("This will write master data to the current site. Continue?"),
				() => this._call(phases, false),
				() => {}
			);
		} else {
			this._call(phases, true);
		}
	}

	_call(phases, dry_run) {
		this.running = true;
		const $btn = dry_run ? this.$("#md-dry") : this.$("#md-apply");
		const other = dry_run ? this.$("#md-apply") : this.$("#md-dry");
		$btn.prop("disabled", true).addClass("btn-primary").removeClass("btn-secondary");
		other.prop("disabled", true);
		this.$("#md-status").html(`<i class="fa fa-spinner fa-spin"></i> ${__("Working...")}`);

		frappe.call({
			method: "fast_entry_app.fast_entry_app.page.fast_master_data.fast_master_data.run_seed",
			args: { dry_run: dry_run ? true : false, phases: phases.join(",") },
			callback: (r) => {
				this.running = false;
				$btn.prop("disabled", false).removeClass("btn-primary").addClass("btn-secondary");
				other.prop("disabled", false);
				this.render_result(r.message);
				if (dry_run) this.load_overview();
			},
			error: () => {
				this.running = false;
				$btn.prop("disabled", false).removeClass("btn-primary").addClass("btn-secondary");
				other.prop("disabled", false);
				this.$("#md-status").html("");
			},
		});
	}

	render_result(m) {
		if (!m) return;
		const summary = m.dry_run ? __("Dry run") : __("Applied");
		this.$("#md-status").html(
			`<span class="${m.failed ? "text-danger" : "text-success"}">${summary}: ${m.created} ${__(
				"created"
			)}, ${m.skipped} ${("skipped")}, ${m.failed} ${("failed")}</span>`
		);

		let html = `
			<div class="md-summary">
				<span class="md-chip md-chip-ok">${m.created} ${__("created")}</span>
				<span class="md-chip md-chip-skip">${m.skipped} ${__("skipped")}</span>
				<span class="md-chip ${m.failed ? "md-chip-bad" : "md-chip-ok"}">${m.failed} ${__("failed")}</span>
			</div>`;

		if (m.failed) {
			html += `<div class="alert alert-danger" style="margin: 10px 0 0;">
				<i class="fa fa-times-circle"></i>
				${__("Nothing was committed: the run is all-or-nothing. Fix the rows below and try again.")}
			</div>`;
			html += `<table class="table table-sm md-table"><thead><tr>
				<th>${__("Doctype")}</th><th>${__("Record")}</th><th>${__("Reason")}</th>
			</tr></thead><tbody>`;
			(m.failures || [])
				.slice(0, 25)
				.forEach(
					(f) => `<tr>
						<td>${this.esc(f.doctype)}</td>
						<td>${this.esc(f.name)}</td>
						<td class="text-danger">${this.esc(f.reason)}</td>
					</tr>`
				);
			html += `</tbody></table>`;
		}

		(m.warnings || []).forEach((w) => {
			html += `<div class="alert alert-warning" style="margin: 10px 0 0;">
				<i class="fa fa-exclamation-triangle"></i> ${this.esc(w.message)}
			</div>`;
		});

		if (m.created_names_total) {
			html += `<div style="margin-top: 10px;" class="text-muted">
				${__("Created a sample of {0} record(s):", [m.created_names_total])}
				${this.esc((m.created_sample || []).join(", "))}
			</div>`;
		}

		if (m.backup_path) {
			html += `<div style="margin-top: 6px;" class="text-muted">
				${__("Rollback manifest")}: <code>${this.esc(m.backup_path)}</code>
			</div>`;
		}

		this.$("#md-result").html(html);
		this.$("#md-result-card").show();
	}
};
