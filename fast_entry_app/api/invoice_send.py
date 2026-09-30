import os

import frappe
from frappe import _

from fast_entry_app.api import openwa

DEFAULT_PRINT_FORMAT = "Custom Sales Invoice"
DEFAULT_PI_PRINT_FORMAT = "Custom Purchase Invoice"
DEFAULT_QUOTATION_PRINT_FORMAT = "Custom Quotation"


# A plausible phone number: E.164 caps at 15 digits; below 8 is a typo, not a number.
MIN_PHONE_DIGITS = 8
MAX_PHONE_DIGITS = 15


def _strip_digits(value):
	return "".join(ch for ch in str(value or "") if ch.isdigit())


def _country_code():
	return _strip_digits(_wa_settings().wa_country_code) or "91"


def _format_mobile(number, country_code="91"):
	"""Normalise a human-typed mobile number to E.164 digits (no +, spaces or dashes).

	Real data is messy, so all of these must resolve to the same chat id:
	    +91-9327802242, +91 93278 02242, (+91) 93278 02242, 91-9327802242,
	    0091-9327802242 (international prefix), 09327802242 (trunk zero), 9327802242
	Returns "" when the result is not a plausible number, so callers can report a
	missing/invalid number instead of sending to a bogus chat id.
	"""
	raw = str(number or "").strip()
	digits = _strip_digits(raw)
	if not digits:
		return ""

	cc = _strip_digits(country_code) or "91"

	# "00" is the international access prefix; a leading "+" also means country-coded.
	had_intl_prefix = raw.startswith("+") or digits.startswith("00")
	if digits.startswith("00"):
		digits = digits[2:]

	# National numbers are often written with a trunk prefix, e.g. 09327802242.
	if digits.startswith("0"):
		trimmed = digits.lstrip("0")
		if len(trimmed) >= 10:
			digits = trimmed

	if had_intl_prefix:
		# Trust an explicit country code, but recover when they typed "+" + a local number.
		if not digits.startswith(cc) and len(digits) <= 10:
			digits = cc + digits
		result = digits
	elif digits.startswith(cc) and len(digits) >= len(cc) + 10:
		result = digits
	else:
		result = cc + digits

	if not (MIN_PHONE_DIGITS <= len(result) <= MAX_PHONE_DIGITS):
		return ""
	return result


def _mobile_error(number):
	"""Human-readable reason a number is unusable, or None when it is fine."""
	if not _strip_digits(number):
		return _("No number given")
	if not _format_mobile(number, _country_code()):
		return _("{0} does not look like a valid phone number.").format(number)
	return None


def _get_si(invoice_name):
	si = frappe.get_doc("Sales Invoice", invoice_name)
	if si.docstatus != 1:
		frappe.throw(_("Sales Invoice {0} is not submitted").format(invoice_name))
	return si


def _invoice_pdf(si, print_format=None):
	pf = print_format or si.get("print_format") or DEFAULT_PRINT_FORMAT
	if pf and not frappe.db.exists("Print Format", pf):
		pf = None
	try:
		return frappe.get_print(si.doctype, si.name, print_format=pf, as_pdf=True, pdf_generator="chrome")
	except Exception:
		return frappe.get_print(si.doctype, si.name, as_pdf=True, pdf_generator="chrome")


def _get_quotation_pdf(quotation_name):
	quo = frappe.get_doc("Quotation", quotation_name)
	pf = DEFAULT_QUOTATION_PRINT_FORMAT
	if pf and not frappe.db.exists("Print Format", pf):
		pf = None
	try:
		return frappe.get_print(quo.doctype, quo.name, print_format=pf, as_pdf=True, pdf_generator="chrome")
	except Exception:
		return frappe.get_print(quo.doctype, quo.name, as_pdf=True, pdf_generator="chrome")


def _get_pi_pdf(purchase_invoice_name):
	pi = frappe.get_doc("Purchase Invoice", purchase_invoice_name)
	pf = DEFAULT_PI_PRINT_FORMAT
	if pf and not frappe.db.exists("Print Format", pf):
		pf = None
	try:
		return frappe.get_print(pi.doctype, pi.name, print_format=pf, as_pdf=True, pdf_generator="chrome")
	except Exception:
		return frappe.get_print(pi.doctype, pi.name, as_pdf=True, pdf_generator="chrome")


def _save_pdf_to_files(pdf_bytes, filename):
	"""Save PDF to Frappe's public files folder and return the public URL."""
	files_dir = os.path.join(frappe.get_site_path("public", "files"))
	os.makedirs(files_dir, exist_ok=True)
	file_path = os.path.join(files_dir, filename)
	with open(file_path, "wb") as f:
		f.write(pdf_bytes)
	site = frappe.utils.get_url()
	return "{0}/files/{1}".format(site, filename)


def _mailto_url(email, subject, body):
	"""Build a mailto: URL for email compose."""
	return "mailto:{0}?subject={1}&body={2}".format(
		email, quote(subject), quote(body)
	)


# ---------------------------------------------------------------------------
# WhatsApp via OpenWA gateway (no WhatsApp Web)
# ---------------------------------------------------------------------------

# Settings + HTTP transport live in `api/openwa.py`; kept as a local alias for readability.
_wa_settings = openwa.wa_settings


def _wa_config_error():
	return {
		"ok": False,
		"not_configured": True,
		"message": _(
			"WhatsApp sending is not configured. In Fast Entry Settings enable "
			"\"WhatsApp Integration\" and set the OpenWA base URL, API key and session ID."
		),
	}


def _doc_party(doc):
	"""Return (party_type, party_name) for SI / Quotation / Purchase Invoice docs."""
	if doc.doctype == "Purchase Invoice":
		return "Supplier", doc.get("supplier")
	return (doc.get("party_type") or "Customer"), (doc.get("party_name") or doc.get("customer"))


def _wa_number_candidates(doc):
	"""Every phone number reachable for a document, in priority order.

	Each candidate records where it came from, so the UI can offer it as a choice and
	know which field to write when the user picks it as the default.
	"""
	cc = _country_code()
	found = []

	def add(value, source, fieldname, doctype=None):
		if _strip_digits(value):
			found.append(
				{
					"value": value,
					"source": source,
					"fieldname": fieldname,
					"doctype": doctype,
					"normalized": _format_mobile(value, cc),
				}
			)

	add(doc.get("contact_mobile"), _("Document"), "contact_mobile")

	contact = doc.get("contact_person")
	if contact:
		contact_values = frappe.db.get_value("Contact", contact, ["mobile_no", "phone"], as_dict=True) or {}
		add(contact_values.get("mobile_no"), _("Contact"), "mobile_no", "Contact")
		add(contact_values.get("phone"), _("Contact (landline)"), "phone", "Contact")

	party_type, party_name = _doc_party(doc)
	if party_type and party_name:
		add(
			frappe.db.get_value(party_type, party_name, "mobile_no"),
			_(party_type),
			"mobile_no",
			party_type,
		)

	# De-duplicate on the normalised value, keeping the highest-priority occurrence.
	seen = set()
	candidates = []
	for c in found:
		if not c["normalized"]:
			continue
		if c["normalized"] in seen:
			continue
		seen.add(c["normalized"])
		c["chat_id"] = "{0}@c.us".format(c["normalized"])
		c["valid"] = True
		candidates.append(c)
	return candidates


def _resolve_wa_chat(doc, number=None):
	"""Resolve the WhatsApp chatId for a doc.

	Priority: an explicitly supplied number, then the stored candidates (document
	contact_mobile, then the Contact person, then the party master).
	Returns (chat_id, mobile) or (None, None).
	"""
	if number:
		chat_id = _wa_chat_id_from_mobile(number)
		return (chat_id, number) if chat_id else (None, None)
	candidates = _wa_number_candidates(doc)
	if not candidates:
		return None, None
	return candidates[0]["chat_id"], candidates[0]["normalized"]


def _wa_chat_id_from_mobile(mobile):
	clean = _format_mobile(mobile, _country_code())
	return "{0}@c.us".format(clean) if clean else None


@frappe.whitelist()
def set_whatsapp_number(doctype, name, mobile, target="document"):
	"""Save a phone number for a document so it becomes the default WhatsApp recipient.

	`target` selects which record is updated:
	    "document" - the invoice's own contact_mobile
	    "contact"  - the linked Contact's mobile_no (and blanks contact_mobile so the
	                 document inherits it)
	    "party"    - the Customer/Supplier master, so every future document benefits
	Returns the refreshed candidate list so the UI can render the new state directly.
	"""
	openwa.require_whatsapp_role()

	if doctype not in ("Sales Invoice", "Purchase Invoice", "Quotation"):
		frappe.throw(_("Unsupported document type {0}").format(doctype))

	problem = _mobile_error(mobile)
	if problem:
		frappe.throw(problem)

	doc = frappe.get_doc(doctype, name)
	normalized = _format_mobile(mobile, _country_code())

	# Documents here are submitted, and `contact_mobile` is not allow-on-submit, so a
	# full doc.save() would be rejected. This is an operational recipient number, not an
	# accounting value, so update the column directly and leave the GL untouched.
	def set_doc_mobile():
		frappe.db.set_value(doctype, name, "contact_mobile", normalized, update_modified=False)

	if target == "document":
		set_doc_mobile()
		saved_on = _("document")

	elif target == "contact":
		contact = doc.get("contact_person")
		if not contact:
			frappe.throw(_("This document has no Contact Person to update."))
		frappe.db.set_value("Contact", contact, "mobile_no", normalized, update_modified=False)
		set_doc_mobile()
		saved_on = _("Contact {0}").format(contact)

	elif target == "party":
		party_type, party_name = _doc_party(doc)
		if not (party_type and party_name):
			frappe.throw(_("This document has no {0} to update.").format(_("party")))
		frappe.db.set_value(party_type, party_name, "mobile_no", normalized, update_modified=False)
		set_doc_mobile()
		saved_on = _("{0} {1}").format(party_type, party_name)

	else:
		frappe.throw(_("Invalid target {0}").format(target))

	frappe.db.commit()
	return {
		"ok": True,
		"saved_on": saved_on,
		"normalized": normalized,
		"chat_id": "{0}@c.us".format(normalized),
		"candidates": _wa_number_candidates(frappe.get_doc(doctype, name)),
	}


def _wa_caption(doc):
	"""Render the configured caption template with {name} {company} {party}."""
	tmpl = (_wa_settings().wa_caption or "Sales Invoice {name} from {company}").strip()
	if not tmpl:
		tmpl = "{doctype} {name} from {company}"
	party_type, party_name = _doc_party(doc)
	party_display = doc.get("customer_name") or doc.get("supplier_name") or doc.get("party_name") or party_name or ""
	return tmpl.format(
		doctype=doc.doctype,
		name=doc.name,
		company=doc.get("company") or "",
		party=party_display or "",
	)


def _openwa_send_document(cfg, chat_id, pdf_bytes, filename, caption):
	"""POST the PDF (base64) to OpenWA's send-document endpoint. Returns (response_dict, error_str)."""
	return openwa.send_document(chat_id, pdf_bytes, filename, caption)


def _send_doc_whatsapp(doc, number=None):
	"""Shared send routine: returns a response dict suitable for the whitelisted callers.
	doc already loaded via frappe.get_doc."""
	cfg = _wa_settings()
	if not cfg.get("whatsapp_enabled"):
		return _wa_config_error()

	party_type, party_name = _doc_party(doc)
	chat_id, mobile = _resolve_wa_chat(doc, number=number)
	if not mobile:
		return {
			"ok": False,
			"missing_field": "mobile_no",
			"party_type": party_type,
			"party_name": party_name,
			"message": _("{0} has no mobile number.").format(party_name),
		}

	wa_pf = cfg.get("wa_print_format") or DEFAULT_PRINT_FORMAT
	pdf = _invoice_pdf(doc, print_format=wa_pf)
	if not pdf:
		frappe.throw(_("Could not generate PDF for {0} {1}").format(doc.doctype, doc.name))

	filename = "{0}.pdf".format(doc.name)
	caption = _wa_caption(doc)
	resp, err = _openwa_send_document(cfg, chat_id, pdf, filename, caption)
	if not resp:
		frappe.log_error(
			"OpenWA send-document failed for {0} {1}: {2}".format(doc.doctype, doc.name, err),
			"invoice_send.py",
		)
		return {
			"ok": False,
			"message": _("WhatsApp send failed: {0}").format(err),
			"name": doc.name,
			"chat_id": chat_id,
		}

	message_id = resp.get("waMessageId") or resp.get("id")
	return {
		"ok": True,
		"name": doc.name,
		"chat_id": chat_id,
		"message_id": message_id,
	}


@frappe.whitelist()
def update_party_field(party_type, party_name, fieldname, value):
	"""Update a field on Customer/Supplier and return success."""
	openwa.require_whatsapp_role()

	if party_type not in ("Customer", "Supplier"):
		frappe.throw(_("Invalid party type"))
	if fieldname not in ("mobile_no", "email_id", "phone"):
		frappe.throw(_("Invalid field"))
	frappe.db.set_value(party_type, party_name, fieldname, value, update_modified=False)
	frappe.db.commit()
	return {"ok": True}


# ---------------------------------------------------------------------------
# Sales Invoice send
# ---------------------------------------------------------------------------

@frappe.whitelist()
def send_invoice_whatsapp(invoice_name, number=None):
	"""Generate PDF and push it to the customer on WhatsApp via the OpenWA gateway (no WhatsApp Web)."""
	si = _get_si(invoice_name)
	return _send_doc_whatsapp(si, number=number)


@frappe.whitelist()
def send_invoice_email(invoice_name, recipient=None):
	"""Email the Sales Invoice PDF to the customer via SMTP."""
	si = _get_si(invoice_name)
	email = recipient or frappe.db.get_value("Customer", si.customer, "email_id")
	if not email:
		return {
			"ok": False,
			"missing_field": "email_id",
			"party_type": "Customer",
			"party_name": si.customer,
			"message": _("Customer {0} has no email address.").format(si.customer),
		}

	pdf = _invoice_pdf(si)
	if not pdf:
		frappe.throw(_("Could not generate PDF for {0} {1}").format(si.doctype, si.name))

	frappe.sendmail(
		recipients=[email],
		subject=_("Sales Invoice {0} from {1}").format(si.name, si.company),
		message=_("Dear {0},<br><br>Please find attached your Sales Invoice <b>{1}</b>.<br><br>Thank you.").format(si.customer_name, si.name),
		attachments=[{"fname": "Sales_Invoice_{0}.pdf".format(si.name), "fcontent": pdf}],
		reference_doctype="Sales Invoice",
		reference_name=si.name,
	)

	return {"ok": True, "name": si.name, "email": email}


# ---------------------------------------------------------------------------
# Quotation send
# ---------------------------------------------------------------------------

@frappe.whitelist()
def send_quotation_whatsapp(quotation_name, number=None):
	"""Generate PDF and push it to the customer on WhatsApp via the OpenWA gateway (no WhatsApp Web)."""
	quo = frappe.get_doc("Quotation", quotation_name)
	return _send_doc_whatsapp(quo, number=number)


@frappe.whitelist()
def send_quotation_email(quotation_name, recipient=None):
	"""Email the Quotation PDF to the customer via SMTP."""
	quo = frappe.get_doc("Quotation", quotation_name)
	email = recipient or frappe.db.get_value("Customer", quo.party_name, "email_id")
	if not email:
		return {
			"ok": False,
			"missing_field": "email_id",
			"party_type": "Customer",
			"party_name": quo.party_name,
			"message": _("Customer {0} has no email address.").format(quo.party_name),
		}

	pdf = _get_quotation_pdf(quotation_name)
	if not pdf:
		frappe.throw(_("Could not generate PDF for {0} {1}").format(quo.doctype, quo.name))

	frappe.sendmail(
		recipients=[email],
		subject=_("Quotation {0} from {1}").format(quo.name, quo.company),
		message=_("Dear {0},<br><br>Please find attached your Quotation <b>{1}</b>.<br><br>Thank you.").format(quo.customer_name, quo.name),
		attachments=[{"fname": "Quotation_{0}.pdf".format(quo.name), "fcontent": pdf}],
		reference_doctype="Quotation",
		reference_name=quo.name,
	)

	return {"ok": True, "name": quo.name, "email": email}


# ---------------------------------------------------------------------------
# Purchase Invoice send
# ---------------------------------------------------------------------------

@frappe.whitelist()
def send_purchase_invoice_whatsapp(purchase_invoice_name, number=None):
	"""Generate PDF and push it to the supplier on WhatsApp via the OpenWA gateway (no WhatsApp Web)."""
	pi = frappe.get_doc("Purchase Invoice", purchase_invoice_name)
	return _send_doc_whatsapp(pi, number=number)


@frappe.whitelist()
def send_purchase_invoice_email(purchase_invoice_name, recipient=None):
	"""Email the Purchase Invoice PDF to the supplier via SMTP."""
	pi = frappe.get_doc("Purchase Invoice", purchase_invoice_name)
	email = recipient or frappe.db.get_value("Supplier", pi.supplier, "email_id")
	if not email:
		return {
			"ok": False,
			"missing_field": "email_id",
			"party_type": "Supplier",
			"party_name": pi.supplier,
			"message": _("Supplier {0} has no email address.").format(pi.supplier),
		}

	pdf = _get_pi_pdf(purchase_invoice_name)
	if not pdf:
		frappe.throw(_("Could not generate PDF for Purchase Invoice {0}").format(pi.name))

	frappe.sendmail(
		recipients=[email],
		subject=_("Purchase Invoice {0} from {1}").format(pi.name, pi.company),
		message=_("Dear {0},<br><br>Please find attached your Purchase Invoice <b>{1}</b>.<br><br>Thank you.").format(pi.supplier, pi.name),
		attachments=[{"fname": "Purchase_Invoice_{0}.pdf".format(pi.name), "fcontent": pdf}],
		reference_doctype="Purchase Invoice",
		reference_name=pi.name,
	)

	return {"ok": True, "name": pi.name, "email": email}
