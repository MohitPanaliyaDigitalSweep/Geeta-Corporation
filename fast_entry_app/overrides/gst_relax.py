"""Keep Sales Invoices on the normal ERPNext flow: never force GSTIN / Address.

Stock ERPNext does not need a customer GSTIN or a Customer Address to save or
submit a Sales Invoice.  India Compliance changes that: the moment an invoice is
e-Invoice *applicable* (a B2B customer with a GSTIN) it throws

    Customer Address is a mandatory field for generating e-Invoices

on **every save**, which blocks the Desk form, our Fast Entry pages, the HRMS
app and the JSON API unless an Address record exists for the customer.

That requirement is relaxed here for **Sales Invoices only**, and only for the
address/GSTIN pair the user asked about:

* Saving a Sales Invoice never fails because ``customer_address`` is empty.
* Such an invoice is marked ``einvoice_status = "Not Applicable"`` (with an
  info log naming the reason) so submitting it never tries to push an
  incomplete invoice to the GST portal.
* Every other GST rule is untouched: tax correctness (IGST vs CGST/SGST),
  place of supply, GSTIN format, reverse charge, HSN codes for invoices that do
  have an address, e-Waybill rules, ... all still run through India
  Compliance.  Explicitly pressing *Generate e-Invoice* on an invoice without
  an address still reports that the address is required, which is the correct
  answer for a deliberate action.

The patch is idempotent and a no-op on sites where India Compliance (or
e-Invoicing) is not installed.
"""

import frappe

_applied = False


def apply():
	"""Wrap India Compliance's e-Invoice status setter (idempotent)."""
	global _applied

	if _applied:
		return

	try:
		import india_compliance.gst_india.overrides.sales_invoice as ic_sales_invoice
	except Exception:
		# India Compliance not installed on this site - nothing to relax.
		return

	original = ic_sales_invoice.validate_fields_and_set_status_for_e_invoice

	if getattr(original, "_fast_entry_relaxed", False):
		_applied = True
		return

	def validate_fields_and_set_status_for_e_invoice(doc, gst_settings=None):
		# Cancellation handling must stay exactly as India Compliance does it.
		if doc.docstatus != 2 and not doc.get("customer_address"):
			# Normal ERPNext flow: the address is optional, so e-Invoice simply
			# does not apply while it is missing (it could never be generated
			# without one anyway - NIC requires it).
			if doc.get("einvoice_status") != "Not Applicable":
				doc.einvoice_status = "Not Applicable"

			frappe.logger("fast_entry_app").info(
				"e-Invoice skipped for %s %s: no Customer Address "
				"(GSTIN/Address are not mandatory on Sales Invoice)",
				doc.doctype,
				doc.name,
			)
			return

		return original(doc, gst_settings)

	validate_fields_and_set_status_for_e_invoice._fast_entry_relaxed = True
	ic_sales_invoice.validate_fields_and_set_status_for_e_invoice = (
		validate_fields_and_set_status_for_e_invoice
	)
	_applied = True
