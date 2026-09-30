import frappe
from frappe import _

no_cache = True

# Per-doctype field map. Column sets differ across these three:
#   - Purchase Invoice has no `customer_name`
#   - Quotation has no `posting_date` (it uses `transaction_date`)
DOCTYPE_SPEC = {
	"Sales Invoice": {
		"party": "customer",
		"party_name": "customer_name",
		"date": "posting_date",
	},
	"Purchase Invoice": {
		"party": "supplier",
		"party_name": "supplier_name",
		"date": "posting_date",
	},
	"Quotation": {
		"party": "party_name",
		"party_name": "customer_name",
		"date": "transaction_date",
	},
}


def get_context(context):
	context.no_breadcrumbs = True
	context.no_header = True
	context.title = "WhatsApp Send"


@frappe.whitelist()
def get_whatsapp_status():
	"""Report whether WhatsApp sending is configured, without leaking secrets."""
	from fast_entry_app.api.invoice_send import _wa_settings

	cfg = _wa_settings()
	return {
		"enabled": bool(cfg.get("whatsapp_enabled")),
		"base_url": cfg.get("wa_base_url") or "",
		"session_id": cfg.get("wa_session_id") or "",
		"has_api_key": bool(cfg.get_password("wa_api_key", raise_exception=False)),
		"print_format": cfg.get("wa_print_format") or "",
	}


@frappe.whitelist()
def get_company_options():
	"""Company names for the filter dropdown."""
	return {"companies": sorted(frappe.get_all("Company", pluck="name"))}


@frappe.whitelist()
def get_sendable_invoices(doctype="Sales Invoice", company=None, limit=50):
	"""List submitted documents that can be sent on WhatsApp, with the resolved mobile."""
	from fast_entry_app.api.invoice_send import (
		_doc_party,
		_format_mobile,
		_resolve_wa_chat,
		_wa_number_candidates,
		_wa_settings,
	)

	if doctype not in DOCTYPE_SPEC:
		frappe.throw(_("Unsupported document type {0}").format(doctype))

	spec = DOCTYPE_SPEC[doctype]
	filters = {"docstatus": 1}
	if company and company != "All":
		filters["company"] = company

	rows = frappe.get_all(
		doctype,
		filters=filters,
		fields=[
			"name",
			spec["party"],
			spec["party_name"],
			"company",
			spec["date"],
			"grand_total",
			"currency",
			"contact_mobile",
		],
		order_by="modified desc",
		limit_page_length=frappe.utils.cint(limit) or 50,
	)

	cc = (_wa_settings().wa_country_code or "91").lstrip("+")
	out = []
	for r in rows:
		doc = frappe.get_doc(doctype, r.name)
		chat_id, mobile = _resolve_wa_chat(doc)
		party = r.get(spec["party"])
		party_display = r.get(spec["party_name"]) or party
		candidates = _wa_number_candidates(doc)
		doc_mobile = (r.get("contact_mobile") or "").strip()
		party_type, party_name = _doc_party(doc)
		# Where the user is allowed to save a new number from this row.
		targets = [{"value": "document", "label": _("This document")}]
		if doc.get("contact_person"):
			targets.append({"value": "contact", "label": _("Contact person")})
		if party_type and party_name:
			targets.append({"value": "party", "label": _("{0} master").format(party_type)})
		out.append(
			{
				"name": r.name,
				"doctype": doctype,
				"party": party,
				"party_display": party_display,
				"company": r.get("company"),
				"doc_date": str(r.get(spec["date"]) or ""),
				"grand_total": r.get("grand_total"),
				"currency": r.get("currency"),
				"mobile": mobile or "",
				"chat_id": chat_id or "",
				"has_mobile": bool(mobile),
				"mobile_source": candidates[0]["source"] if candidates else "",
				# All reachable numbers, so the user can add one or pick a different default.
				"candidates": candidates,
				"save_targets": targets,
				"stored_mobile": doc_mobile,
				# A number typed on the document that could not be parsed: needs fixing.
				"stored_mobile_invalid": bool(doc_mobile) and not _format_mobile(doc_mobile, cc),
			}
		)
	return {"invoices": out, "country_code": cc}
