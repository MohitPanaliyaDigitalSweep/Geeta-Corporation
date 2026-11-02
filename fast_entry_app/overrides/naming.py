# Copyright (c) 2026, Geeta Corporation and contributors
# License: MIT. See LICENSE
"""Company + financial-year based Sales Invoice numbering.

Series::

    <ABBR>/<6 digits>/<YY-YY>        e.g.  GC/000001/26-27

Why this needs its own ``autoname()`` instead of a plain ``naming_series:``
template: Frappe derives the counter key from the text rendered *before* the
number part. Because the financial year sits *after* the number here, a stock
template such as ``GC/.######./26-27`` would key the counter on ``GC/`` and the
number would keep running across years (GC/000245/26-27 -> GC/000246/27-28).

We therefore keep the DocType autoname as ``naming_series:`` (so Frappe still
handles amendments, prompts and manual naming) and only fill ``name`` first:

* counter key = ``<ABBR>/<YY-YY>/`` -> restarts at 000001 every financial year
* the visible template ``<ABBR>/.######./<YY-YY>`` is stored on
  ``naming_series`` so the form shows the series the number came from

India Compliance caps a GST invoice number at 16 characters, so
``GOC/000001/26-27`` already sits exactly on the limit: any company
abbreviation longer than 3 characters produces an invalid invoice number.
"""

import frappe
from frappe.model.naming import getseries
from frappe.utils import getdate

#: digits in the running number (000001)
COUNTER_DIGITS = 6

#: India Compliance: GST invoice number length limit
GST_NAME_MAX_LENGTH = 16

#: legacy series kept in the dropdown so existing/other flows still resolve
LEGACY_SERIES = (
	"SINV-.YY.-",
	"SRET-.YY.-",
	"ACC-SINV-.YYYY.-",
	"ACC-SINV-RET-.YYYY.-",
)

MANAGED_DOCTYPE = "Sales Invoice"


def fiscal_year_short(date, company=None) -> str | None:
	"""Return ``26-27`` for the fiscal year containing ``date`` (``None`` if no FY)."""
	from erpnext.accounts.utils import get_fiscal_year

	fiscal_year = get_fiscal_year(date=getdate(date), company=company, raise_on_missing=False)
	if not fiscal_year:
		return None

	_start, end = getdate(fiscal_year[1]), getdate(fiscal_year[2])
	return f"{_start:%y}-{end:%y}"


def invoice_series(doc) -> tuple[str, str] | None:
	"""Return ``(counter_key, template)`` for ``doc``, or ``None`` when undeterminable.

	``counter_key``  = ``GC/26-27/``   -> tabSeries row, restarts every FY
	``template``     = ``GC/.######./26-27`` -> renders ``GC/000001/26-27``
	"""
	company = doc.get("company") or frappe.db.get_default("company")
	if not company:
		return None

	abbr = frappe.db.get_value("Company", company, "abbr")
	if not abbr:
		return None

	date = doc.get("posting_date") or doc.get("transaction_date") or frappe.utils.today()
	fiscal_year = fiscal_year_short(date, company=company)
	if not fiscal_year:
		return None

	return f"{abbr}/{fiscal_year}/", f"{abbr}/.{'#' * COUNTER_DIGITS}./{fiscal_year}"


def make_invoice_number(doc) -> str | None:
	"""Next ``GC/000001/26-27`` for ``doc``, or ``None`` to fall back to naming_series."""
	series = invoice_series(doc)
	if not series:
		# No fiscal year covers this date (ERPNext refuses such invoices anyway).
		# Keep the stock naming path away from our per-FY template so it cannot
		# hand out a number that our own counter will later try to reuse.
		if not doc.get("naming_series") or "/.######./" in doc.naming_series:
			doc.naming_series = LEGACY_SERIES[0]
		return None

	counter_key, template = series
	abbr, fiscal_year = counter_key.split("/")[0], counter_key.split("/")[1]
	name = f"{abbr}/{getseries(counter_key, COUNTER_DIGITS)}/{fiscal_year}"

	doc.naming_series = template

	if len(name) > GST_NAME_MAX_LENGTH:
		frappe.msgprint(
			frappe._(
				"Invoice number {0} is {1} characters long; India Compliance allows "
				"at most {2}. Shorten the company abbreviation."
			).format(frappe.bold(name), len(name), GST_NAME_MAX_LENGTH),
			title=frappe._("GST invoice number too long"),
			indicator="orange",
			alert=True,
		)

	return name


@frappe.whitelist()
def get_naming_series_for_company(company, posting_date=None) -> str | None:
	"""Return the per-company/per-FY naming-series template for ``company``.

	Used by the client to auto-select the right series when the company (or the
	posting date's fiscal year) changes on a Sales Invoice form. Returns ``None``
	when the company abbreviation or fiscal year cannot be resolved, in which
	case the client leaves the field untouched.
	"""
	if not company:
		return None
	abbr = frappe.db.get_value("Company", company, "abbr")
	if not abbr:
		return None
	if not posting_date:
		posting_date = frappe.utils.today()
	try:
		short = fiscal_year_short(posting_date, company=company)
	except Exception:
		short = None
	if not short:
		return None
	return f"{abbr}/.{'#' * COUNTER_DIGITS}./{short}"


def sync_invoice_series_options() -> None:
	"""Keep the Naming Series dropdown and the amendment rule in sync (idempotent).

	* Dropdown options are generated from the current companies + current
	  financial year, so the form can display the series the number came from.
	  Purely cosmetic: :func:`make_invoice_number` is authoritative.
	* Amendments must take a *fresh* number. Frappe's default ``Amend Counter``
	  appends ``-1`` which would make ``GC/000001/26-27-1`` (17 chars) and be
	  rejected by India Compliance, so Sales Invoice is pinned to
	  ``Default Naming``.
	"""
	options: list[str] = []
	if frappe.db.table_exists("Company") and frappe.db.table_exists("Fiscal Year"):
		fiscal_year = fiscal_year_short(frappe.utils.today())
		if fiscal_year:
			for abbr in frappe.get_all("Company", pluck="abbr", order_by="name"):
				options.append(f"{abbr}/.{'#' * COUNTER_DIGITS}./{fiscal_year}")
	options.extend(LEGACY_SERIES)
	options = list(dict.fromkeys(options))

	_set_naming_series_options("\n".join(options))
	_set_amendment_rule()


def _set_naming_series_options(value: str) -> None:
	if not frappe.db.table_exists("Property Setter"):
		return

	filters = {
		"doc_type": MANAGED_DOCTYPE,
		"field_name": "naming_series",
		"property": "options",
	}
	existing = frappe.db.exists("Property Setter", filters)
	if not existing:
		frappe.get_doc(
			{
				"doctype": "Property Setter",
				"doctype_or_field": "DocField",
				**filters,
				"property_type": "Text",
				"value": value,
			}
		).insert(ignore_permissions=True)
		return

	doc = frappe.get_doc("Property Setter", existing)
	if doc.value != value:
		doc.value = value
		doc.save(ignore_permissions=True)


def _set_amendment_rule() -> None:
	if not frappe.db.table_exists("Amended Document Naming Settings"):
		return

	existing = frappe.db.get_value(
		"Amended Document Naming Settings",
		{"document_type": MANAGED_DOCTYPE},
		"name",
	)
	if existing:
		if (
			frappe.db.get_value("Amended Document Naming Settings", existing, "action")
			!= "Default Naming"
		):
			frappe.db.set_value(
				"Amended Document Naming Settings", existing, "action", "Default Naming"
			)
		return

	settings = frappe.get_single("Document Naming Settings")
	settings.append(
		"amend_naming_override",
		{"document_type": MANAGED_DOCTYPE, "action": "Default Naming"},
	)
	settings.flags.ignore_permissions = True
	settings.save()
