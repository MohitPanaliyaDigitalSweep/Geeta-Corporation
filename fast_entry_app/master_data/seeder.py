"""Load business master data (Company, Items, Customers, Suppliers, Addresses,
Contacts and the scaffolding they need) into a site from a bundle.

**Why this is not a Frappe ``fixtures/`` entry.** Adding a doctype to
``hooks.fixtures`` makes ``sync_fixtures()`` re-import those records on *every*
``bench migrate``. Because that import path runs with ``force=True``
(``frappe/modules/import_file.py:128``) it always reaches
``delete_old_doc()`` (``:229``), which calls
``frappe.delete_doc(..., force=1, for_reload=True)`` (``:273``).
``for_reload=True`` skips the link check, ``on_trash`` and the
permission/submitted guard, and sets ``delete_permanently = True`` -- so there
is no Trash and no recovery. Masters shipped as fixtures would be hard-deleted
and recreated on every migrate, reverting client edits and orphaning posted
invoices. Also, ``import_fixtures`` only catches ``ImportError`` and
``frappe.DoesNotExistError`` (``frappe/utils/fixtures.py:47``), so a single bad
record aborts ``install-app``/``migrate`` mid-run, after a per-file commit.

This module is therefore **opt-in and idempotent-by-skip**: it runs when you
ask it to, never deletes anything, and reports what it did.

The idempotency and safety patterns are copied from ERPNext's own Setup Wizard
machinery -- ``frappe.desk.page.setup_wizard.setup_wizard.make_records``
(savepoint + rollback + ``ignore_if_duplicate``) and
``erpnext.setup.setup_wizard.operations.install_fixtures.get_preset_records``
(``__condition`` lambdas) -- plus ``erpnext/setup/demo.py``, which is likewise
manual, savepoint-wrapped and never wired to ``after_install``.

Naming
------
Records are inserted with ``frappe.flags.in_import`` set, which preserves an
explicitly supplied ``name`` (``frappe/model/naming.py:158``) and then skips
every other naming path (``:184-191``). So a party keeps the name it has in the
bundle instead of being handed a ``CUST-2026-00001``, and identity is a plain
``frappe.db.exists(doctype, name)`` check. It also skips the framework's link
validation, so this module does its own link pre-check and reports dangling
references loudly rather than writing them silently.

Usage::

    # preview
    bench --site <site> execute \\
        fast_entry_app.master_data.seeder.seed --kwargs '{"dry_run": true}'
    # apply
    bench --site <site> execute \\
        fast_entry_app.master_data.seeder.seed --kwargs '{"dry_run": false}'
"""

import json
import os
import traceback

import frappe
from frappe import _

# Dependency-ordered. Each phase runs fully before the next starts, because a
# later phase links to the earlier ones. The order is the whole point.
PHASES = [
	{
		"phase": "Foundations",
		"doctypes": ["Item Group", "Customer Group", "Supplier Group", "Territory", "UOM", "Price List", "Warehouse Type", "Gender"],
		"detail": "Group trees, territories, units of measure, price lists and warehouse types.",
	},
	{
		"phase": "Fiscal Year",
		"doctypes": ["Fiscal Year"],
		"detail": "Must exist before a Company, which adopts one as its default.",
	},
	{
		"phase": "Companies",
		"doctypes": ["Company"],
		"detail": (
			"Heaviest step. ERPNext's Company.on_update builds the chart of "
			"accounts, default warehouses, cost centre and departments."
		),
	},
	{
		"phase": "Warehouses",
		"doctypes": ["Warehouse"],
		"detail": "Company-scoped; warehouses Company already created are skipped.",
	},
	{
		"phase": "Items",
		"doctypes": ["Item"],
		"detail": "Product catalogue, including the Option B UOM table.",
	},
	{
		"phase": "Item Prices",
		"doctypes": ["Item Price"],
		"detail": "Validates the Item exists and the UOM is in its UOM table.",
	},
	{
		"phase": "Parties",
		"doctypes": ["Customer", "Supplier"],
		"detail": "Customers before suppliers so a transporter supplier is available.",
	},
	{
		"phase": "Addresses & Contacts",
		"doctypes": ["Address", "Contact"],
		"detail": "Dynamic links back to the parties loaded in the previous phase.",
	},
]

SAVEPOINT = "master_data_seed"

# Bundles committed to the app, in resolution order. ``geeta_reference.json`` is
# the verbatim Geeta master data (real party/contact/address names), which is
# what a fresh site should load. ``geeta_anonymised.json`` keeps the same
# structure with every identifying value replaced, for anyone who must not ship
# the reference names.
REFERENCE_BUNDLES = ("geeta_reference.json", "geeta_anonymised.json")

# Self-referential parent link on each tree doctype. Children are exported
# before their root (single-doctype trees have no dedicated phase ordering), so
# `seed()` re-orders each doctype parent-first to keep both the link pre-check
# and the actual insert happy when the target site is completely empty.
PARENT_FIELD = {
	"Item Group": "parent_item_group",
	"Customer Group": "parent_customer_group",
	"Supplier Group": "parent_supplier_group",
	"Territory": "parent_territory",
	"Warehouse": "parent_warehouse",
}


def resolve_bundle_path(bundle_path=None):
	"""Locate the bundle to load.

	Defaults to the verbatim ``geeta_reference.json`` committed to the repo, so a
	fresh site receives the *same* customers, suppliers, addresses and contacts
	by name. ``geeta_anonymised.json`` is the fallback: identical structure, but
	party/contact/address names replaced with ``Customer 001``-style labels for
	situations where the reference data must not be redistributed.

	A live export is never in git -- pass its path explicitly, or copy it to
	``sites/<site>/private/files/master_data_export.json`` which is what
	:func:`fast_entry_app.master_data.export.export_bundle` writes.
	"""
	if bundle_path:
		if not os.path.isabs(bundle_path):
			bundle_path = frappe.get_site_path(bundle_path)
		if not os.path.exists(bundle_path):
			frappe.throw(f"Bundle not found: {bundle_path}")
		return bundle_path

	for filename in REFERENCE_BUNDLES:
		committed = frappe.get_app_path("fast_entry_app", "master_data", "bundles", filename)
		if os.path.exists(committed):
			return committed

	fallback = frappe.get_site_path("private", "files", "master_data_export.json")
	if os.path.exists(fallback):
		return fallback

	frappe.throw(
		"No master data bundle found. Expected one of "
		f"{', '.join(REFERENCE_BUNDLES)} in the app's master_data/bundles folder, or a "
		f"bundle at {fallback}. Generate one with "
		"fast_entry_app.master_data.export.export_bundle."
	)


def load_bundle(bundle_path=None):
	path = resolve_bundle_path(bundle_path)
	with open(path) as handle:
		bundle = json.load(handle)
	if bundle.get("version") != 1:
		frappe.throw(f"Unsupported bundle version {bundle.get('version')!r} in {path}")
	bundle["_path"] = path
	return bundle


# --------------------------------------------------------------------------
# per-record helpers
# --------------------------------------------------------------------------


def _link_fields(doctype):
	"""(fieldname, options) for every plain Link field on the doctype."""
	meta = frappe.get_meta(doctype)
	return [(df.fieldname, df.options) for df in meta.get_link_fields() if df.options]


def _missing_links(doctype, record, known=None):
	"""Link values in ``record`` that do not resolve on this site.

	The framework's own link validation is disabled while ``in_import`` is set,
	so a dangling reference would otherwise be written silently and only surface
	later, inside an unrelated transaction. Checking here turns that into a
	reported failure.

	``known`` holds ``(doctype, name)`` pairs this run has already created, or
	would create on a dry run. Without it a preview is useless: every Address
	would be reported as dangling because the Customer it links to has not been
	written yet.
	"""
	known = known or set()

	def resolves(target_doctype, target_name):
		return (target_doctype, target_name) in known or frappe.db.exists(target_doctype, target_name)

	missing = []
	for fieldname, options in _link_fields(doctype):
		value = record.get(fieldname)
		if not value or not isinstance(value, str):
			continue
		if options in ("", "User", "DocType"):
			continue
		if not resolves(options, value):
			missing.append(f"{fieldname} -> {options}: {value}")

	# Dynamic links (Contact/Address -> Customer/Supplier)
	for link in record.get("links") or []:
		link_doctype = link.get("link_doctype")
		link_name = link.get("link_name")
		if link_doctype and link_name and not resolves(link_doctype, link_name):
			missing.append(f"links -> {link_doctype}: {link_name}")

	return missing


def _clean_record(doctype, record):
	"""Strip the bundle's own metadata and anything the doctype does not have."""
	doc = frappe.new_doc(doctype)
	for fieldname, value in record.items():
		if fieldname in ("doctype", "name"):
			continue
		if doc.meta.get_field(fieldname):
			doc.set(fieldname, value)

	# ``links`` is a real child table on Contact/Address, set it explicitly.
	if record.get("links") and doc.meta.get_field("links"):
		for link in record["links"]:
			if link.get("link_doctype") and link.get("link_name"):
				doc.append("links", {"link_doctype": link["link_doctype"], "link_name": link["link_name"]})

	# Preserve the bundle's name; in_import makes set_new_name() honour it.
	doc.name = record.get("name")
	doc.flags.name_set = False
	return doc


# Doctypes whose ``name`` is a *server-generated random token* rather than a
# stable business key. Frappe hashes these on every insert, so the name that a
# bundle exported from another site can never match what the target site mints
# (Item Price -> "hejdogtnkv" on one site, "47r4mu5nnv" on another). Matching on
# name therefore always reports "missing", and the re-insert then trips the
# ERPNext uniqueness check ("Item Price appears multiple times based on Price
# List, Supplier/Customer, Currency, Item, Batch, UOM, Qty, and Dates").
#
# For these, identity is the *business* key, so probe on that instead. This is
# what makes a second seeding run idempotent.
_IDENTITY_KEYS = {
	"Item Price": ("item_code", "price_list", "selling", "buying", "currency", "uom"),
}


def _exists(doctype, name, record=None):
	"""True when this bundle record is already on the site.

	Uses the record's business identity for doctypes with server-generated
	names (see :data:`_IDENTITY_KEYS`) and the document name for everything
	else. ``record`` is optional so existing callers keep working.
	"""
	if doctype in _IDENTITY_KEYS and record:
		filters = {}
		for fieldname in _IDENTITY_KEYS[doctype]:
			value = record.get(fieldname)
			if value in (None, ""):
				continue
			filters[fieldname] = value
		if filters:
			return bool(frappe.db.exists(doctype, filters))

	return bool(name) and bool(frappe.db.exists(doctype, name))


def _order_parents_first(doctype, docs):
	"""Reorder a doctype's records so tree parents precede their children.

	The exporter emits records in ``frappe.get_all`` order, which on a populated
	site happens to list leaves before the ``All ...`` roots. On a brand-new
	site every node is absent, so the dry run's link pre-check would flag every
	child as dangling because its parent has not been "created" yet -- and a
	real insert would break the same way. Sort depth-first so the root lands
	first; folds are impossible in ERPNext NestedSets (children point up).
	"""
	parent_field = PARENT_FIELD.get(doctype)
	if not parent_field:
		return docs

	by_name = {doc.get("name"): doc for doc in docs}
	depths = {}

	def depth(name, seen=()):
		if name in depths:
			return depths[name]
		record = by_name.get(name)
		parent = record.get(parent_field) if record else None
		if not parent or parent in seen or parent not in by_name:
			d = 0
		else:
			d = depth(parent, seen + (name,)) + 1
		depths[name] = d
		return d

	return sorted(docs, key=lambda doc: (depth(doc.get("name")), doc.get("name") or ""))


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def seed(bundle_path=None, dry_run=True, only=None, company=None):
	"""Load a master data bundle into this site.

	:param bundle_path: path to a bundle. Defaults to the committed anonymised
	    one, then to ``sites/<site>/private/files/master_data_export.json``.
	:param dry_run: **default True** -- compute the plan and write nothing.
	:param only: optional list of phase names or doctypes to restrict the run.
	:param company: optional list of Companies to limit Companies / Warehouses to.

	Returns a report dict. Never raises for a single bad record: failures are
	collected per record so one bad row cannot lose the other 1,028.
	"""
	frappe.only_for(("System Manager",))

	bundle = load_bundle(bundle_path)
	records = bundle.get("records", {})
	only_lower = {o.lower() for o in (only or [])}

	phases = []
	for spec in PHASES:
		doctypes = list(spec["doctypes"])
		if company and "Company" in doctypes:
			doctypes = [d for d in doctypes if d != "Company"]
			doctypes = doctypes + ["Company"]
		if only_lower and not (
			spec["phase"].lower() in only_lower or any(d.lower() in only_lower for d in doctypes)
		):
			continue
		phases.append({**spec, "doctypes": doctypes})

	report = {
		"bundle": bundle["_path"],
		"anonymised": bool(bundle.get("anonymised")),
		"dry_run": dry_run,
		"site": frappe.local.site,
		"phases": [],
		"created": 0,
		"skipped": 0,
		"failed": 0,
		"failures": [],
		"warnings": [],
		"created_names": [],
	}

	previous_in_import = frappe.flags.in_import
	previous_mute = frappe.flags.mute_emails
	frappe.flags.in_import = True
	frappe.flags.mute_emails = True

	# (doctype, name) pairs this run has created or would create, so a later
	# phase can resolve links to an earlier phase's records -- essential for
	# the dry run to be a faithful simulation.
	known = set()
	backup = {}

	try:
		for spec in phases:
			phase_report = {
				"phase": spec["phase"],
				"detail": spec["detail"],
				"doctypes": [],
			}
			for doctype in spec["doctypes"]:
				bundle_docs = records.get(doctype, [])
				if company and doctype in ("Company", "Warehouse"):
					bundle_docs = [d for d in bundle_docs if d.get("company", True) in company]
				# Tree doctypes must seed roots before children, or every child
				# fails its own link check on a fresh site.
				bundle_docs = _order_parents_first(doctype, bundle_docs)

				dt_report = {"doctype": doctype, "created": 0, "skipped": 0, "failed": 0}
				for record in bundle_docs:
					name = record.get("name")
					result, reason = _seed_one(doctype, record, dry_run=dry_run, known=known)
					dt_report[result] += 1
					if result == "failed":
						report["failed"] += 1
						report["failures"].append(
							{
								"phase": spec["phase"],
								"doctype": doctype,
								"name": name,
								"reason": reason or "unknown",
							}
						)
					elif result == "skipped":
						report["skipped"] += 1
					else:
						report["created"] += 1
						report["created_names"].append(f"{doctype}:{name}")
						if doctype in ("Customer", "Supplier", "Item", "Company", "UOM", "Item Group"):
							backup.setdefault(doctype, []).append(name)

				phase_report["doctypes"].append(dt_report)
			report["phases"].append(phase_report)

		if not dry_run and not report["failed"]:
			_warnings_and_followups(report, records)
			_write_backup(backup, report)
			_set_default_fiscal_year(records)
			frappe.db.commit()

	except Exception:
		frappe.db.rollback(save_point=SAVEPOINT)
		raise
	finally:
		frappe.flags.in_import = previous_in_import
		frappe.flags.mute_emails = previous_mute

	report["backup_path"] = None if dry_run else _backup_path()
	if dry_run:
		report["note"] = "Dry run -- nothing was written. Re-run with dry_run=false to apply."

	return report


def _seed_one(doctype, record, dry_run, known):
	"""Return ``(status, reason)`` where status is created | skipped | failed."""
	name = record.get("name")
	if _exists(doctype, name, record) or (doctype, name) in known:
		known.add((doctype, name))
		return "skipped", None

	if dry_run:
		# Surface problems during the preview instead of at write time.
		missing = _missing_links(doctype, record, known=known)
		if missing:
			return "failed", "dangling link(s): " + "; ".join(missing)
		known.add((doctype, name))
		return "created", None

	frappe.db.savepoint(SAVEPOINT)
	try:
		doc = _clean_record(doctype, record)
		doc.insert(ignore_permissions=True, ignore_if_duplicate=True)
		known.add((doctype, name))
		frappe.clear_last_message()
		return "created", None
	except Exception:
		# Capture the human message BEFORE clearing: _last_error() reads the
		# message log, which clear_last_message() wipes.
		reason = _last_error() or "unknown"
		frappe.clear_last_message()
		frappe.db.rollback(save_point=SAVEPOINT)
		frappe.log_error(
			title=f"Master data seed failed: {doctype} {name}",
			message=traceback.format_exc(),
		)
		return "failed", reason


def _last_error():
	"""Best-effort human message from the messages thrown during the insert."""
	log = frappe.get_message_log() or []
	for message in reversed(log):
		if isinstance(message, str) and message:
			return message[:300]
		if isinstance(message, dict):
			text = message.get("message") or message.get("title")
			if text:
				return frappe.utils.strip_html(str(text))[:300]
	return None


# --------------------------------------------------------------------------
# follow-ups that matter for this app
# --------------------------------------------------------------------------


def _warnings_and_followups(report, records):
	"""Surface the app-specific consequences of what was just loaded."""
	# Option B: Fast Entry books in pieces and get_invoice_uom() refuses to save
	# for an item stocked in anything other than Nos.
	try:
		offenders = frappe.get_all(
			"Item",
			filters={"stock_uom": ["!=", "Nos"], "is_stock_item": 1},
			pluck="name",
			limit=200,
		)
		if offenders:
			report["warnings"].append(
				{
					"kind": "option_b_required",
					"message": (
						f"{len(offenders)} stock item(s) are not stocked in Nos "
						"(e.g. " + ", ".join(offenders[:3]) + "). Fast Entry will refuse to "
						"save against them. Run: bench --site "
						f"{frappe.local.site} execute "
						"fast_entry_app.maintenance.stock_uom_to_pieces.execute "
						"--kwargs '{\"dry_run\": false}'"
					),
				}
			)
	except Exception:
		pass

	# UOM anchor invariant that ERPNext itself enforces.
	bad_anchor = frappe.db.sql(
		"""
		SELECT i.name, u.conversion_factor
		FROM `tabItem` i
		JOIN `tabUOM Conversion Detail` u
			ON u.parent = i.name AND u.parenttype = 'Item'
		WHERE i.stock_uom = u.uom AND u.conversion_factor != 1
		LIMIT 5
		"""
	)
	if bad_anchor:
		report["warnings"].append(
			{
				"kind": "uom_anchor",
				"message": (
					"These items have a conversion factor other than 1 on their own stock "
					"UOM, which ERPNext rejects: "
					+ ", ".join(f"{n} (cf={cf})" for n, cf in bad_anchor)
				),
			}
		)

	# Item Price rows that the bundle asked for but that no longer resolve.
	if "Item Price" in records:
		unresolved = frappe.get_all(
			"Item Price",
			filters={"price_list": ["in", [d.get("price_list") for d in records.get("Price List", [])]]},
			pluck="name",
		)
		if not unresolved:
			report["warnings"].append(
				{"kind": "no_item_prices", "message": "No Item Prices resolved; check the price lists."}
			)


def _set_default_fiscal_year(records):
	"""Point the site at a Fiscal Year if it has none.

	A bare ERPNext install has no Fiscal Year and no default, and a Company
	adopts whatever ``frappe.db.get_default('fiscal_year')`` says. Without this
	the site's books have no period to post against.
	"""
	try:
		if frappe.db.get_default("fiscal_year"):
			return
		fiscal_years = records.get("Fiscal Year", [])
		if not fiscal_years:
			return
		name = fiscal_years[0].get("name")
		if not _exists("Fiscal Year", name):
			return
		frappe.db.set_default("fiscal_year", name)
		# Link it to every seeded company so Company lookups resolve.
		for company in frappe.get_all("Company", pluck="name"):
			if frappe.db.exists("Fiscal Year Company", {"fiscal_year": name, "company": company}):
				continue
			frappe.get_doc(
				{"doctype": "Fiscal Year Company", "parent": name, "parenttype": "Fiscal Year", "company": company}
			).insert(ignore_permissions=True)
	except Exception:
		frappe.clear_last_message()
		frappe.log_error(title="Master data: could not set default fiscal year")


def _backup_path():
	return frappe.get_site_path("private", "files", "master_data_seed_backup.json")


def _write_backup(backup, report):
	"""Record exactly what we created, so a rollback script has a manifest."""
	if not backup:
		return
	path = _backup_path()
	os.makedirs(os.path.dirname(path), exist_ok=True)
	payload = {
		"site": frappe.local.site,
		"seeded_at": frappe.utils.now_datetime().isoformat(),
		"bundle": report["bundle"],
		"created": backup,
	}
	with open(path, "w") as handle:
		json.dump(payload, handle, indent=1, sort_keys=True)
