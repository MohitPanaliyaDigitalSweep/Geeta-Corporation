"""Create the custom fields and property setters this app adds to ERPNext.

This module is the single source of truth for the schema Fast Entry App layers
on top of ERPNext. It is used from three places, so it must stay idempotent:

- ``fixtures/custom_field.json`` handles the normal case (app installed last).
- ``patches/v2_ensure_erpnext_fields.py`` repairs sites where the app was
  installed before ERPNext, which silently produced no fields at all.
- manual ``bench execute`` when someone adds a new ERPNext doctype later.

Two rules matter here:

1. Never require ERPNext to already be present. Every doctype is checked with
   ``frappe.db.table_exists`` and skipped when missing, so running this on a
   bare frappe site is a clean no-op instead of an exception.
2. Only ever create ``fe_*`` fields owned by this app. The Item-level
   ``custom_box``/``custom_pcs``/``custom_ltr``/``custom_mrp`` fields seen on
   some sites were added by hand outside this app and are deliberately not
   managed here.
"""

import frappe

MODULE = "Fast Entry App"

# Item child tables that carry the per-line pack breakdown.
ITEM_TABLES = [
	"Purchase Invoice Item",
	"Sales Invoice Item",
	"Quotation Item",
	"Sales Order Item",
	"Purchase Order Item",
	"Delivery Note Item",
	"Purchase Receipt Item",
	"Stock Entry Detail",
	"Asset Capitalization Service Item",
	"Asset Movement Item",
	"BOM Creator Item",
	"BOM Item",
	"BOM Secondary Item",
	"BOM Website Item",
	"Bill of Entry Item",
	"Blanket Order Item",
	"Installation Note Item",
	"Landed Cost Item",
	"Material Request Item",
	"Opportunity Item",
	"POS Invoice Item",
	"Packed Item",
	"Packing Slip Item",
	"Pick List Item",
	"Product Bundle Item",
	"Request for Quotation Item",
	"Serial and Batch Entry",
	"Stock Reconciliation Item",
	"Subcontracting Inward Order Item",
	"Subcontracting Inward Order Service Item",
	"Subcontracting Order Item",
	"Subcontracting Order Service Item",
	"Subcontracting Receipt Item",
	"Supplier Quotation Item",
	"Work Order Additional Item",
]

# Item table columns: Item | Item Name | Accepted Qty | Box | PCS | LTR | Total LTR | Rate | Amount.
# (doc_type, field_name, property, value, property_type)
PROPERTY_SETTERS = [
	("Purchase Invoice Item", "item_name", "in_list_view", "1", "Check"),
	("Sales Invoice Item", "item_name", "in_list_view", "1", "Check"),
	("Sales Invoice Item", "warehouse", "in_list_view", "0", "Check"),
	("Sales Invoice Item", "qty", "label", "Accepted Qty", "Data"),
	# Do NOT force a default on Sales/Purchase Invoice.update_stock — let
	# ERPNext's own default control it. Fast Entry sets it explicitly from the
	# payload below (1 when ticked, 0 when unticked), so unticking truly
	# prevents stock impact. A Property Setter default of "1" would override
	# ERPNext's default and leak through on unchecked invoices.
	# A collapsible Section Break with no collapsible_depends_on renders
	# COLLAPSED by default (frappe/public/js/frappe/form/layout.js:500-511:
	# `collapse = true` unless the depends_on expression is truthy). The
	# "Additional Discount" section holds discount_amount + apply_discount_on,
	# so it was hidden on the standard Sales Invoice form. Auto-expand it
	# whenever a discount is present so the Net Total / discount is visible.
	("Sales Invoice", "additional_discount_section", "collapsible_depends_on", "eval:doc.discount_amount", "Data"),
]


def _item_table_fields():
	"""fe_box / fe_pcs / fe_ltr / fe_total_ltr for every item child table."""
	fields = []
	for dt in ITEM_TABLES:
		fields.extend(
			[
				{
					"dt": dt,
					"fieldname": "fe_box",
					"fieldtype": "Float",
					"label": "Box",
					"insert_after": "qty",
					"in_list_view": 1,
					"module": MODULE,
					"default": "0",
				},
				{
					"dt": dt,
					"fieldname": "fe_pcs",
					"fieldtype": "Float",
					"label": "PCS",
					"insert_after": "fe_box",
					"in_list_view": 1,
					"module": MODULE,
					# Editable on purpose: PCS is the primary quantity (rate is
					# per-PCS), so it must be typeable. Box and PCS stay in sync
					# both ways in the UI -- see erpnext_pi_override.js calc_row.
					# Keep in sync with fixtures/custom_field.json.
					"read_only": 0,
					"default": "0",
				},
				{
					"dt": dt,
					"fieldname": "fe_ltr",
					"fieldtype": "Float",
					"label": "LTR",
					"insert_after": "fe_pcs",
					"in_list_view": 1,
					"module": MODULE,
					"read_only": 1,
					"default": "0",
				},
				{
					"dt": dt,
					"fieldname": "fe_total_ltr",
					"fieldtype": "Float",
					"label": "Total LTR",
					"insert_after": "fe_ltr",
					"in_list_view": 1,
					"module": MODULE,
					"read_only": 1,
					"default": "0",
				},
			]
		)
	return fields


def _party_fields():
	"""Payment grouping so consolidated payments can be tracked."""
	return [
		{
			"dt": "Supplier",
			"fieldname": "fe_group",
			"fieldtype": "Link",
			"label": "Payment Group",
			"options": "Party Group",
			"insert_after": "supplier_group",
			"module": MODULE,
			"description": "Suppliers with the same group (e.g. IOCL) are paid together as one account",
		},
		{
			"dt": "Customer",
			"fieldname": "fe_group",
			"fieldtype": "Link",
			"label": "Payment Group",
			"options": "Party Group",
			"insert_after": "customer_group",
			"module": MODULE,
			"description": "Customers with the same group are consolidated for payment as one account",
		},
	]


def _sales_invoice_fields():
	"""Sales person on the invoice, plus the fingerprint used to stop double saves."""
	return [
		{
			"dt": "Sales Invoice",
			"fieldname": "fe_sales_person",
			"fieldtype": "Data",
			"label": "Sales Person",
			"insert_after": "contact_person",
			"module": MODULE,
		},
		{
			"dt": "Sales Invoice",
			"fieldname": "fe_dedup_key",
			"fieldtype": "Data",
			"label": "Fast Entry Dedup Key",
			"insert_after": "fe_sales_person",
			"module": MODULE,
			"read_only": 1,
			"hidden": 1,
		},
	]


# Keys that are safe to keep in sync on an already existing field.
_UPDATABLE = (
	"label",
	"insert_after",
	"in_list_view",
	"read_only",
	"hidden",
	"default",
	"options",
	"description",
	"module",
)


def _purchase_invoice_fields():
	"""Fingerprint used to stop double saves on Purchase Invoices."""
	return [
		{
			"dt": "Purchase Invoice",
			"fieldname": "fe_dedup_key",
			"fieldtype": "Data",
			"label": "Fast Entry Dedup Key",
			"insert_after": "bill_no",
			"module": MODULE,
			"read_only": 1,
			"hidden": 1,
		},
	]


def _employee_fields():
	"""Custom fields on Employee (HRMS) for location tracking consent."""
	if not frappe.db.table_exists("Employee"):
		return []
	return [
		{
			"dt": "Employee",
			"fieldname": "location_tracking_consent",
			"fieldtype": "Check",
			"label": "Location Tracking Consent",
			"default": "1",
			"description": "Allow this employee's location to be tracked and shown on the Live Map.",
			"insert_after": "status",
		},
	]


def _customer_location_fields():
	"""Custom fields on Customer/Supplier for map location."""
	fields = []
	if frappe.db.table_exists("Customer"):
		fields.append({
			"dt": "Customer",
			"fieldname": "geolocation",
			"fieldtype": "Geolocation",
			"label": "Location",
			"description": "Customer location on map.",
			"insert_after": "customer_primary_address",
		})
	if frappe.db.table_exists("Supplier"):
		fields.append({
			"dt": "Supplier",
			"fieldname": "geolocation",
			"fieldtype": "Geolocation",
			"label": "Location",
			"description": "Supplier location on map.",
			"insert_after": "supplier_primary_address",
		})
	return fields


def get_field_definitions():
	"""All app-owned custom fields, in creation order."""
	return (
		_item_table_fields()
		+ _party_fields()
		+ _sales_invoice_fields()
		+ _purchase_invoice_fields()
		+ _employee_fields()
		+ _customer_location_fields()
	)


def execute():
	created, updated, skipped = _ensure_custom_fields()
	created_ps, updated_ps = _apply_property_setters()
	frappe.db.commit()
	print(
		f"Fast Entry App schema: {created} created, {updated} updated, "
		f"{skipped} doctypes not installed yet; "
		f"property setters {created_ps} created / {updated_ps} updated"
	)


def _ensure_custom_fields():
	created = updated = skipped = 0
	for f in get_field_definitions():
		dt = f["dt"]

		# ERPNext (and therefore this doctype) may not be installed yet. Skipping
		# is safe: the same definitions are re-checked on the next migrate.
		if not frappe.db.table_exists(dt):
			skipped += 1
			continue

		existing = frappe.db.exists("Custom Field", {"dt": dt, "fieldname": f["fieldname"]})
		if not existing:
			cf = frappe.new_doc("Custom Field")
			cf.update(f)
			cf.insert(ignore_permissions=True)
			created += 1
			print(f"Created: {dt} - {f['fieldname']}")
			continue

		cf = frappe.get_doc("Custom Field", existing)
		cf.flags.ignore_validate = True
		changed = False
		for key in _UPDATABLE:
			if key in f and cf.get(key) != f[key]:
				cf.set(key, f[key])
				changed = True
		if changed:
			cf.save(ignore_permissions=True)
			updated += 1
			print(f"Updated: {dt} - {f['fieldname']}")

	return created, updated, skipped


def _apply_property_setters():
	created = updated = 0
	for doc_type, field_name, property, value, property_type in PROPERTY_SETTERS:
		if not frappe.db.table_exists(doc_type):
			continue
		exists = frappe.db.exists(
			"Property Setter",
			{
				"doc_type": doc_type,
				"field_name": field_name,
				"property": property,
			},
		)
		if not exists:
			frappe.get_doc(
				{
					"doctype": "Property Setter",
					# mandatory since v16; "DocField" = this tweaks one field
					"doctype_or_field": "DocField",
					"doc_type": doc_type,
					"field_name": field_name,
					"property": property,
					"property_type": property_type,
					"value": value,
				}
			).insert(ignore_permissions=True)
			created += 1
			print(f"Property Setter created: {doc_type} {field_name} {property}={value}")
		else:
			ps = frappe.get_doc("Property Setter", exists)
			if str(ps.value) != str(value):
				ps.value = value
				ps.save(ignore_permissions=True)
				updated += 1
				print(f"Property Setter updated: {doc_type} {field_name} {property}={value}")

	return created, updated
