import frappe
from frappe import _
from frappe.utils import flt

from erpnext.controllers.taxes_and_totals import calculate_taxes_and_totals as _EngineBase


class calculate_taxes_and_totals(_EngineBase):
	"""True ERPNext "Grand Total" discount, with a never-zero guard.

	Stock ERPNext already does the right thing on ``apply_discount_on == "Grand
	Total"``: the discount is reverse-distributed into the item net amounts (net
	becomes 1830.51 for a subtotal of 2000 with a discount of 200) and deducted
	overall from the grand total (2160). The tax rows keep the full-rate amount
	and the GL posts the effective value. That is the behaviour we want, so we do
	NOT change it here.

	The only addition: stock allows ``discount >= total`` (which would collapse
	the grand total to zero or below). We throw a clear error instead. The guard
	only applies to the Grand Total mode, so a genuine Net Total 100%-off free
	invoice still works.

	``overrides/controllers.py`` wires this engine into Sales Invoice, Purchase
	Invoice and Quotation.
	"""

	def get_total_for_discount_amount(self):
		total = super().get_total_for_discount_amount()

		if (
			self.doc.get("apply_discount_on") == "Grand Total"
			and flt(self.doc.get("discount_amount")) > 0
			and (flt(total) <= 0 or flt(self.doc.get("discount_amount")) >= flt(total))
		):
			frappe.throw(
				_(
					"Additional Discount Amount ({0}) cannot be greater than or equal to "
					"the total before such discount ({1}). The transaction cannot become zero."
				).format(
					frappe.format(flt(self.doc.get("discount_amount")), "Currency"),
					frappe.format(flt(total), "Currency"),
				),
				title=_("Invalid Discount Amount"),
			)

		return total
