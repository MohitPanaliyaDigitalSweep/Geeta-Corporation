"""Export business master data from the current site into a seeder bundle.

This is the read-only counterpart of :mod:`fast_entry_app.master_data.seeder`:
it reads masters out of a running site and writes a single JSON bundle that
``seeder.seed()`` can load into another site.

**The bundle contains real personal data** (customer GSTINs, contact phone
numbers, street addresses). Never commit the output. The repo ships only
``bundles/geeta_anonymised.json``, which is produced by
:mod:`fast_entry_app.master_data.anonymise`.

Usage::

    bench --site dev.localhost execute \\
        fast_entry_app.master_data.export.export_bundle
    # -> sites/dev.localhost/private/files/master_data_export.json

``bundle_path`` lets you write somewhere specific; it defaults to the site's
private files folder, which is never web-accessible and never in git.
"""

import json
import os

import frappe

# Fields that must never be carried into a bundle. Some are audit/ownership
# bookkeeping, but a few (owner, creation) are also personal data.
EXCLUDED_FIELDS = {
	"creation",
	"modified",
	"modified_by",
	"owner",
	"parent",
	"parentfield",
	"parenttype",
	"idx",
	"docstatus",
	"_user_tags",
	"_comments",
	"_assign",
	"_liked_by",
	"version",
	"image",
	"signature",
}

# Ordered export plan. Order matters only for readability of the bundle; the
# seeder re-orders by phase. ``fields`` keeps the export small and stable --
# an Item with every ERP column is far larger than the seeder needs.
EXPORT_PLAN = {
	"Item Group": {"fields": ["item_group_name", "parent_item_group", "is_group"]},
	"Customer Group": {"fields": ["customer_group_name", "parent_customer_group", "is_group"]},
	"Supplier Group": {"fields": ["supplier_group_name", "parent_supplier_group", "is_group"]},
	"Territory": {"fields": ["territory_name", "parent_territory", "is_group"]},
	"UOM": {"fields": ["uom_name"]},
	"Price List": {"fields": ["price_list_name", "currency", "selling", "buying", "enabled"]},
	"Warehouse Type": {"fields": ["description"]},
	"Gender": {"fields": ["gender"]},
	"Warehouse": {"fields": ["warehouse_name", "warehouse_type", "company", "is_group", "parent_warehouse"]},
	"Fiscal Year": {"fields": ["year", "year_start_date", "year_end_date", "disabled"]},
	"Company": {
		"fields": [
			"company_name",
			"abbr",
			"default_currency",
			"country",
			"domain",
			"company_type",
			"company_description",
			"date_of_establishment",
			"pan",
			"gstin",
			"tax_id",
			"phone_no",
			"email",
			"website",
		]
	},
	"Item": {
		"fields": [
			"item_code",
			"item_name",
			"item_group",
			"stock_uom",
			"description",
			"brand",
			"gst_hsn_code",
			"is_stock_item",
			"is_sales_item",
			"is_purchase_item",
			"is_dummy",
		],
		"children": {"uoms": ["uom", "conversion_factor"]},
	},
	"Item Price": {
		"fields": ["item_code", "price_list", "price_list_rate", "uom", "selling", "buying", "currency", "valid_from"]
	},
	"Customer": {
		"fields": [
			"customer_name",
			"customer_group",
			"territory",
			"gstin",
			"pan",
			"gst_category",
			"mobile_no",
			"email_id",
			"default_price_list",
			"default_currency",
			"disabled",
		]
	},
	"Supplier": {
		"fields": [
			"supplier_name",
			"supplier_group",
			"is_transporter",
			"gstin",
			"pan",
			"gst_category",
			"mobile_no",
			"email_id",
			"default_price_list",
			"default_currency",
			"disabled",
		]
	},
	"Address": {
		"fields": [
			"address_title",
			"address_type",
			"address_line1",
			"address_line2",
			"city",
			"county",
			"state",
			"gst_state",
			"country",
			"pincode",
			"gstin",
			"phone",
			"fax",
			"is_primary_address",
			"is_shipping_address",
			"disabled",
		]
	},
	"Contact": {
		"fields": [
			"first_name",
			"last_name",
			"company_name",
			"email_id",
			"mobile_no",
			"gender",
			"is_primary_contact",
			"is_billing_contact",
			"is_shipping_contact",
			"disabled",
		]
	},
}

# Dynamic Link rows we must carry so a Contact/Address stays attached to its
# party. These are child rows on the doc itself, plus the "links" child table
# that ERPNext uses to record a contact's links.
LINK_DOCTYPES = ["Contact", "Address"]

# Doctypes whose ``gstin`` is validated (state prefix + PAN + entity + Z +
# base-36 check digit) on every write, so a bad value would abort a seed.
GSTIN_DOCTYPES = ["Company", "Customer", "Supplier", "Address"]


def _clean(doc, fields, children=None):
	"""Project a doc down to ``fields`` plus declared child tables."""
	out = {"doctype": doc.doctype, "name": doc.name}
	for fieldname in fields:
		value = doc.get(fieldname)
		if value is not None and value != "":
			out[fieldname] = value

	for child_doctype, child_fields in (children or {}).items():
		rows = []
		for row in doc.get(child_doctype) or []:
			clean = {}
			for fieldname in child_fields:
				value = row.get(fieldname)
				if value is not None and value != "":
					clean[fieldname] = value
			if clean:
				rows.append(clean)
		if rows:
			out[child_doctype] = rows

	for fieldname in EXCLUDED_FIELDS:
		out.pop(fieldname, None)

	return out


def _export_link_rows(doc):
	"""Capture ERPNext's ``links`` child table (Contact <-> Customer, etc.)."""
	rows = []
	for row in doc.get("links") or []:
		if row.get("link_doctype") and row.get("link_name"):
			rows.append(
				{
					"link_doctype": row.get("link_doctype"),
					"link_name": row.get("link_name"),
				}
			)
	return rows


def _repair_gstin(doc, doctype, repaired):
	"""Fix or drop a GSTIN that would fail validation on the target site.

	A GSTIN can exist on the source site yet be rejected on insert, because
	india_compliance validates the base-36 check digit on every write. Test and
	demo data is the usual culprit -- a hand-typed ``27ABCDE1234F1Z5`` passes
	through the UI but is arithmetically wrong. Such a record makes the whole
	seed abort (the run is atomic), so repair it here instead.

	The state code and PAN are preserved and only the check digit is
	recomputed, which keeps the record exercising the same GST code paths.
	When even that is not possible the GSTIN is cleared and the party is
	demoted to Unregistered rather than blocking the entire bundle.
	"""
	gstin = (doc.get("gstin") or "").strip()
	if not gstin:
		return

	from fast_entry_app.master_data.anonymise import CODE_POINTS, make_valid_gstin

	if len(gstin) == 15 and CODE_POINTS.find(gstin[14]) >= 0:
		base, factor, total = gstin[:14], 1, 0
		for char in base:
			digit = factor * CODE_POINTS.find(char)
			digit = (digit // 36) + (digit % 36)
			total += digit
			factor = 2 if factor == 1 else 1
		expected = CODE_POINTS[(36 - (total % 36)) % 36]
		if expected == gstin[14]:
			return
		fixed = base + expected
	else:
		# Wrong shape entirely: keep the state prefix, rebuild a valid tail.
		pan = gstin[2:12] if len(gstin) >= 12 else ""
		if not _valid_pan(pan):
			doc["gstin"] = ""
			doc["gst_category"] = "Unregistered"
			repaired.append({"doctype": doctype, "name": doc.get("name"), "from": gstin, "to": ""})
			return
		fixed = make_valid_gstin(gstin[:2], pan)

	doc["gstin"] = fixed
	repaired.append({"doctype": doctype, "name": doc.get("name"), "from": gstin, "to": fixed})


def _valid_pan(pan):
	return (
		isinstance(pan, str)
		and len(pan) == 10
		and pan[:5].isalpha()
		and pan[4].isalpha()
		and pan[5:9].isdigit()
		and pan[9].isalpha()
	)


def export_bundle(bundle_path=None, company=None, doctypes=None, include_disabled=True):
	"""Write a JSON bundle of business masters from the current site.

	:param bundle_path: absolute path to write. Defaults to
	    ``sites/<site>/private/files/master_data_export.json``.
	:param company: optional list of Companies to scope Warehouses/Item Price to.
	:param doctypes: optional list of doctypes to restrict the export to.
	:param include_disabled: keep records with ``disabled=1``.
	"""
	frappe.only_for(("System Manager",))

	repaired = []
	plan = EXPORT_PLAN
	if doctypes:
		unknown = set(doctypes) - set(EXPORT_PLAN)
		if unknown:
			frappe.throw(f"Unknown doctype(s) in export plan: {sorted(unknown)}")
		plan = {dt: EXPORT_PLAN[dt] for dt in doctypes}

	companies = frappe.get_all("Company", pluck="name")
	if company:
		companies = [c for c in companies if c in company]
		if not companies:
			frappe.throw(f"No matching Company in {company}")

	bundle = {
		"version": 1,
		"generated_on": frappe.utils.now_datetime().isoformat(),
		"generated_from_site": frappe.local.site,
		"anonymised": False,
		"companies": companies,
		"records": {},
		"counts": {},
	}

	for doctype, spec in plan.items():
		names = frappe.get_all(doctype, pluck="name")
		# Child doctypes that are scoped by company in practice. Item Price
		# rows have no company column of their own but do resolve a currency,
		# so filter via the price list's company where possible.
		if doctype in ("Warehouse",):
			allowed = frappe.get_all(
				"Warehouse", filters={"company": ["in", companies]}, pluck="name"
			)
			names = allowed

		docs = []
		for name in names:
			try:
				doc = frappe.get_doc(doctype, name)
			except frappe.DoesNotExistError:
				continue

			if not include_disabled and doc.get("disabled"):
				continue
			if doctype == "Item Price" and company:
				if not _item_price_in_companies(doc, companies):
					continue

			cleaned = _clean(doc, spec["fields"], spec.get("children"))
			if doctype in GSTIN_DOCTYPES:
				_repair_gstin(cleaned, doctype, repaired)
			if doctype in LINK_DOCTYPES:
				links = _export_link_rows(doc)
				if links:
					cleaned["links"] = links
			docs.append(cleaned)

		bundle["records"][doctype] = docs
		bundle["counts"][doctype] = len(docs)

	if not bundle_path:
		bundle_path = frappe.get_site_path("private", "files", "master_data_export.json")
	os.makedirs(os.path.dirname(bundle_path), exist_ok=True)

	with open(bundle_path, "w") as handle:
		json.dump(bundle, handle, indent=1, sort_keys=True, default=str)

	return {
		"path": bundle_path,
		"counts": bundle["counts"],
		"total_docs": sum(bundle["counts"].values()),
		"companies": companies,
		"gstin_repaired": repaired,
	}


def _item_price_in_companies(doc, companies):
	"""An Item Price belongs to a company through its Price List."""
	price_list = doc.get("price_list")
	if not price_list:
		return True
	# Price List has no company column; fall back to currency matching so we
	# still drop rows that clearly belong to another company's books.
	company_currencies = set()
	for company in companies:
		currency = frappe.db.get_value("Company", company, "default_currency")
		if currency:
			company_currencies.add(currency)
	if not doc.get("currency"):
		return True
	return doc.get("currency") in company_currencies
