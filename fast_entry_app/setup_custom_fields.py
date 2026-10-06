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
]

# Item table columns: Item | Item Name | Accepted Qty | Box | PCS | LTR | Total LTR | Rate | Amount.
# (doc_type, field_name, property, value, property_type)
PROPERTY_SETTERS = [
	("Purchase Invoice Item", "item_name", "in_list_view", "1", "Check"),
	("Sales Invoice Item", "item_name", "in_list_view", "1", "Check"),
	("Sales Invoice Item", "warehouse", "in_list_view", "0", "Check"),
	("Sales Invoice Item", "qty", "label", "Accepted Qty", "Data"),
	# Pre-tick "Update Stock" on new manual Sales/Purchase Invoices in the
	# standard ERPNext form. This lives at the metadata level (not just the
	# client script in erpnext_pi_override.js) so it works regardless of
	# browser cache or whether that script loads. Never put this in a fixture:
	# a Property Setter whose doc_type is an ERPNext doctype crashes install
	# when ERPNext is absent. Stay editable (users may still uncheck for
	# service / consolidated invoices).
	("Sales Invoice", "update_stock", "default", "1", "Check"),
	("Purchase Invoice", "update_stock", "default", "1", "Check"),
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


def get_field_definitions():
	"""All app-owned custom fields, in creation order."""
	return _item_table_fields() + _party_fields() + _sales_invoice_fields()


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
