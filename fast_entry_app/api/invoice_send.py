import os
from urllib.parse import quote

import frappe
from frappe import _

DEFAULT_PRINT_FORMAT = "Custom Sales Invoice"
DEFAULT_PI_PRINT_FORMAT = "Custom Purchase Invoice"
DEFAULT_QUOTATION_PRINT_FORMAT = "Custom Quotation"


def _format_mobile(number):
	"""Normalize mobile number to WhatsApp format: country code + number, no + or spaces."""
	digits = "".join(c for c in str(number) if c.isdigit() or c == "+")
	if digits.startswith("+"):
		digits = digits[1:]
	country_code = "91"
	if not digits.startswith(country_code):
		digits = country_code + digits
	return digits


def _get_si(invoice_name):
	si = frappe.get_doc("Sales Invoice", invoice_name)
	if si.docstatus != 1:
		frappe.throw(_("Sales Invoice {0} is not submitted").format(invoice_name))
	return si


def _invoice_pdf(si):
	pf = si.get("print_format") or DEFAULT_PRINT_FORMAT
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


def _wa_send_url(number, text):
	"""Build a wa.me/send URL that opens WhatsApp chat with the contact."""
	clean = _format_mobile(number)
	return "https://wa.me/{0}?text={1}".format(clean, quote(text or ""))


@frappe.whitelist()
def update_party_field(party_type, party_name, fieldname, value):
	"""Update a field on Customer/Supplier and return success."""
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
	"""Generate PDF, save to files, return PDF download URL + WhatsApp chat URL."""
	si = _get_si(invoice_name)
	mobile = number or frappe.db.get_value("Customer", si.customer, "mobile_no")
	if not mobile:
		return {
			"ok": False,
			"missing_field": "mobile_no",
			"party_type": "Customer",
			"party_name": si.customer,
			"message": _("Customer {0} has no mobile number.").format(si.customer),
		}

	pdf = _invoice_pdf(si)
	if not pdf:
		frappe.throw(_("Could not generate PDF for {0} {1}").format(si.doctype, si.name))

	pdf_filename = "Sales_Invoice_{0}.pdf".format(si.name)
	pdf_url = _save_pdf_to_files(pdf, pdf_filename)

	text = _("Sales Invoice {0} from {1}").format(si.name, si.company)
	wa_url = _wa_send_url(mobile, text)

	return {"ok": True, "name": si.name, "pdf_url": pdf_url, "wa_url": wa_url}


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
	"""Generate PDF, save to files, return PDF download URL + WhatsApp chat URL."""
	quo = frappe.get_doc("Quotation", quotation_name)
	mobile = number or frappe.db.get_value("Customer", quo.party_name, "mobile_no")
	if not mobile:
		return {
			"ok": False,
			"missing_field": "mobile_no",
			"party_type": "Customer",
			"party_name": quo.party_name,
			"message": _("Customer {0} has no mobile number.").format(quo.party_name),
		}

	pdf = _get_quotation_pdf(quotation_name)
	if not pdf:
		frappe.throw(_("Could not generate PDF for {0} {1}").format(quo.doctype, quo.name))

	pdf_filename = "Quotation_{0}.pdf".format(quo.name)
	pdf_url = _save_pdf_to_files(pdf, pdf_filename)

	text = _("Quotation {0} from {1}").format(quo.name, quo.company)
	wa_url = _wa_send_url(mobile, text)

	return {"ok": True, "name": quo.name, "pdf_url": pdf_url, "wa_url": wa_url}


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
	"""Generate PDF, save to files, return PDF download URL + WhatsApp chat URL."""
	pi = frappe.get_doc("Purchase Invoice", purchase_invoice_name)
	mobile = number or frappe.db.get_value("Supplier", pi.supplier, "mobile_no")
	if not mobile:
		return {
			"ok": False,
			"missing_field": "mobile_no",
			"party_type": "Supplier",
			"party_name": pi.supplier,
			"message": _("Supplier {0} has no mobile number.").format(pi.supplier),
		}

	pdf = _get_pi_pdf(purchase_invoice_name)
	if not pdf:
		frappe.throw(_("Could not generate PDF for Purchase Invoice {0}").format(pi.name))

	pdf_filename = "Purchase_Invoice_{0}.pdf".format(pi.name)
	pdf_url = _save_pdf_to_files(pdf, pdf_filename)

	text = _("Purchase Invoice {0} from {1}").format(pi.name, pi.company)
	wa_url = _wa_send_url(mobile, text)

	return {"ok": True, "name": pi.name, "pdf_url": pdf_url, "wa_url": wa_url}


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
