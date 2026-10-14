from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
	SalesInvoice as _SalesInvoiceBase,
)
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import (
	PurchaseInvoice as _PurchaseInvoiceBase,
)
from erpnext.selling.doctype.quotation.quotation import Quotation as _QuotationBase

from fast_entry_app.overrides.taxes_and_totals import calculate_taxes_and_totals


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
