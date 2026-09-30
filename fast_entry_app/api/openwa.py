"""Shared OpenWA gateway client: settings lookup + generic JSON transport.

The gateway (https://github.com/rmyndharis/OpenWA) is a self-hosted WhatsApp REST bridge.
This module is the only place that knows how to talk HTTP to it; every other module
(send helpers, session management) goes through :func:`request`.
"""

import base64
import json
import urllib.error
import urllib.request

import frappe
from frappe import _

DEFAULT_BASE_URL = "http://127.0.0.1:2785"
REQUEST_TIMEOUT = 60

# Roles allowed to drive the WhatsApp bridge and edit recipient numbers.
# Mirrors the roles the "WhatsApp Send" page is already restricted to, so anyone
# who can open the page can still use it.
ALLOWED_ROLES = (
	"System Manager",
	"Sales User",
	"Sales Manager",
	"Purchase User",
	"Purchase Manager",
	"Accounts User",
	"Accounts Manager",
)


def require_whatsapp_role():
	"""Block callers who must not manage the WhatsApp bridge.

	The session endpoints expose the pairing QR, can request a pairing code and
	can unlink the linked device, and the number setters rewrite contact details
	on customers, suppliers and their contacts. None of that should be reachable
	by every logged-in user, so these entry points check the caller's roles.
	"""
	if frappe.session.user == "Administrator":
		return
	if set(frappe.get_roles()) & set(ALLOWED_ROLES):
		return
	frappe.throw(
		_("Not permitted to manage WhatsApp settings or recipient numbers."),
		frappe.PermissionError,
	)


def wa_settings():
	"""Return the Fast Entry Settings single as the WhatsApp config source."""
	return frappe.get_single("Fast Entry Settings")


def _config_error():
	return _(
		"WhatsApp is not configured. In Fast Entry Settings enable "
		"\"WhatsApp Integration\" and set the OpenWA base URL, API key and session ID."
	)


def base_url():
	return str(wa_settings().wa_base_url or DEFAULT_BASE_URL).rstrip("/")


def session_id():
	return wa_settings().wa_session_id or ""


def api_key():
	# `get_password` is required: a Password field returns "********" via get().
	return wa_settings().get_password("wa_api_key", raise_exception=False) or ""


def request(path, method="GET", data=None, timeout=REQUEST_TIMEOUT):
	"""Call an OpenWA API path. Returns (parsed_json, error_str); error is None on success."""
	if not session_id():
		return None, _("No OpenWA session ID configured.")
	if "{session}" in path:
		path = path.replace("{session}", session_id())
	url = base_url() + path
	key = api_key()
	if not key:
		return None, _("No OpenWA API key configured.")

	payload = None if data is None else json.dumps(data).encode("utf-8")
	req = urllib.request.Request(
		url,
		data=payload,
		headers={"Content-Type": "application/json", "X-API-Key": key},
		method=method,
	)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as resp:
			raw = resp.read().decode("utf-8")
			return (json.loads(raw) if raw.strip() else {}), None
	except urllib.error.HTTPError as e:
		detail = e.read().decode("utf-8", "replace")
		# Surface the gateway's own message where possible; it is far more useful than the status.
		try:
			body = json.loads(detail)
			msg = body.get("message") or body.get("error") or detail
			if isinstance(msg, (dict, list)):
				msg = json.dumps(msg)
		except Exception:
			msg = detail
		return None, "{0} {1}: {2}".format(e.code, e.reason, str(msg)[:300])
	except Exception as e:
		return None, str(e)


def send_document(chat_id, pdf_bytes, filename, caption):
	"""POST a PDF (base64) to OpenWA's send-document endpoint. Returns (response, error)."""
	return request(
		"/api/sessions/{session}/messages/send-document",
		method="POST",
		data={
			"chatId": chat_id,
			"base64": base64.b64encode(pdf_bytes).decode("utf-8"),
			"mimetype": "application/pdf",
			"filename": filename,
			"caption": caption,
		},
	)
