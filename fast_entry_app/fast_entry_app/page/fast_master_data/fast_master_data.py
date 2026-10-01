"""Whitelisted helpers for the "Load Master Data" page.

Thin wrappers around :mod:`fast_entry_app.master_data.seeder`. All of them are
restricted to System Manager in two independent places -- the Page doctype's
``roles`` list gates desk visibility, and :func:`_require_system_manager` gates
the endpoint itself, so a crafted API call cannot bypass the UI restriction.
"""

import frappe

# Only these phases may be requested individually, and only this subset is
# meaningful on its own. "Companies" without "Fiscal Year" is rejected by the
# seeder's own ordering, not silently ignored.
ALLOWED_PHASES = [
	"Foundations",
	"Fiscal Year",
	"Companies",
	"Warehouses",
	"Items",
	"Item Prices",
	"Parties",
	"Addresses & Contacts",
]


def _require_system_manager():
	if "System Manager" not in frappe.get_roles(frappe.session.user):
		frappe.throw(
			"Only a System Manager can load master data.",
			frappe.PermissionError,
		)


def _csv(value):
	if not value:
		return []
	if isinstance(value, (list, tuple)):
		return [str(v).strip() for v in value if str(v).strip()]
	return [part.strip() for part in str(value).split(",") if part.strip()]


@frappe.whitelist()
def get_seed_overview():
	"""Bundle metadata, available phases, and what this site already has.

	Called on page load so the operator can see the blast radius before doing
	anything. Deliberately does not run the plan -- that is the separate
	"Dry Run" action, because it touches every record.
	"""
	_require_system_manager()
	from fast_entry_app.master_data.seeder import PHASES, load_bundle

	bundle = load_bundle()

	existing = {}
	for doctype in ("Item", "Customer", "Supplier", "Address", "Contact", "Company", "Item Price", "UOM"):
		existing[doctype] = frappe.db.count(doctype)

	return {
		"bundle_path": bundle["_path"],
		"anonymised": bool(bundle.get("anonymised")),
		"generated_on": bundle.get("generated_on"),
		"bundle_counts": bundle.get("counts", {}),
		"total_docs": sum(bundle.get("counts", {}).values()),
		"phases": [
			{
				"phase": p["phase"],
				"detail": p["detail"],
				"doctypes": p["doctypes"],
				"docs": sum(bundle.get("counts", {}).get(d, 0) for d in p["doctypes"]),
			}
			for p in PHASES
		],
		"existing": existing,
	}


@frappe.whitelist()
def run_seed(dry_run=True, phases=None, bundle_path=None):
	"""Preview or apply the seed. ``dry_run`` defaults to True on both sides.

	The client is not trusted for the default: an omitted or falsy-ish
	``dry_run`` still results in a preview unless the caller passes the literal
	``False``, so a malformed request cannot accidentally write 1,029 records.
	"""
	_require_system_manager()
	from fast_entry_app.master_data.seeder import seed

	requested = _csv(phases)
	unknown = [p for p in requested if p not in ALLOWED_PHASES]
	if unknown:
		frappe.throw(f"Unknown phase(s): {', '.join(unknown)}")

	apply_changes = dry_run is False or str(dry_run).lower() == "false"

	report = seed(
		bundle_path=bundle_path or None,
		dry_run=not apply_changes,
		only=requested or None,
	)

	# The report can carry a few thousand created names; the UI only needs a
	# short sample plus the counts.
	created_names = report.pop("created_names", [])
	report["created_sample"] = created_names[:25]
	report["created_names_total"] = len(created_names)
	report["failures"] = report["failures"][:100]
	return report
