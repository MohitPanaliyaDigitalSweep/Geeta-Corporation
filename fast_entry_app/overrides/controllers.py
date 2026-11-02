from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
	SalesInvoice as _SalesInvoiceBase,
)
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import (
	PurchaseInvoice as _PurchaseInvoiceBase,
)
from erpnext.selling.doctype.quotation.quotation import Quotation as _QuotationBase

from fast_entry_app.overrides.gst_relax import apply as _apply_gst_relax
from fast_entry_app.overrides.taxes_and_totals import calculate_taxes_and_totals

# Imported for every Sales Invoice instance (override_doctype_class), i.e. always
# before validate() runs, so India Compliance sees the relaxed e-Invoice status
# setter.  Keeps GSTIN / Customer Address optional, like stock ERPNext.
_apply_gst_relax()


class SalesInvoice(_SalesInvoiceBase):
	def calculate_taxes_and_totals(self):
		calculate_taxes_and_totals(self)

		if self.doctype in (
			"Sales Order",
			"Delivery Note",
			"Sales Invoice",
			"POS Invoice",
		):
			self.calculate_commission()
			self.calculate_contribution()


class PurchaseInvoice(_PurchaseInvoiceBase):
	def calculate_taxes_and_totals(self):
		calculate_taxes_and_totals(self)


class Quotation(_QuotationBase):
	def calculate_taxes_and_totals(self):
		calculate_taxes_and_totals(self)
