"""Shared GOWA gateway client: settings lookup + generic HTTP transport.

GOWA (https://github.com/aldinokemal/go-whatsapp-web-multidevice) is a self-hosted
WhatsApp REST bridge written in Go (single binary, ~15 MB RSS, no Chromium).
This module is the only place that knows how to talk HTTP to it; every other module
(send helpers, session management) goes through :func:`request`.

OpenWA (api/openwa.py) is kept in the repo for future reference but is no longer
the active transport — GOWA replaces it.
"""

import base64
import io
import json

import frappe
import qrcode
import requests
from frappe import _

DEFAULT_BASE_URL = "http://127.0.0.1:3000"
DEFAULT_USERNAME = "admin"
DEFAULT_DEVICE_ID = "fast-sales"
REQUEST_TIMEOUT = 60

# Roles allowed to drive the WhatsApp bridge and edit recipient numbers.
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
	"""Block callers who must not manage the WhatsApp bridge."""
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
		"\"WhatsApp Integration\" and set the GOWA base URL, username, password and device ID."
	)


def base_url():
	return str(wa_settings().wa_base_url or DEFAULT_BASE_URL).rstrip("/")


def username():
	return (wa_settings().get("wa_username") or DEFAULT_USERNAME or "").strip()


def password():
	# wa_api_key field is repurposed as the GOWA Basic Auth password.
	pw = wa_settings().get_password("wa_api_key", raise_exception=False)
	return pw or ""


def device_id():
	# wa_session_id field is repurposed as the GOWA device ID.
	return (wa_settings().get("wa_session_id") or DEFAULT_DEVICE_ID or "").strip()


def _auth_header():
	creds = "{0}:{1}".format(username(), password())
	return "Basic " + base64.b64encode(creds.encode("utf-8")).decode("ascii")


def _headers():
	h = {"Authorization": _auth_header()}
	did = device_id()
	if did:
		h["X-Device-Id"] = did
	return h


def request(path, method="GET", data=None, files=None, timeout=REQUEST_TIMEOUT):
	"""Call a GOWA API path. Returns (parsed_json, error_str); error is None on success.

	`path` may contain `{device}` which is replaced with the configured device ID.
	"""
	if not device_id():
		return None, _("No GOWA device ID configured.")
	if "{device}" in path:
		path = path.replace("{device}", device_id())
	url = base_url() + path

	try:
		if files:
			resp = requests.request(
				method, url, headers=_headers(), files=files, data=data, timeout=timeout
			)
		elif data is not None:
			resp = requests.request(
				method, url, headers={**_headers(), "Content-Type": "application/json"},
				json=data, timeout=timeout,
			)
		else:
			resp = requests.request(method, url, headers=_headers(), timeout=timeout)

		raw = resp.text
		if resp.status_code >= 400:
			try:
				body = json.loads(raw)
				msg = body.get("message") or body.get("error") or raw
			except Exception:
				msg = raw
			return None, "{0} {1}: {2}".format(resp.status_code, resp.reason, str(msg)[:300])

		if not raw.strip():
			return {}, None
		try:
			return json.loads(raw), None
		except Exception:
			return {"raw": raw}, None
	except requests.exceptions.ConnectionError as e:
		return None, str(e)[:200]
	except requests.exceptions.Timeout as e:
		return None, "Request timed out: {0}".format(str(e)[:200])
	except Exception as e:
		return None, str(e)[:200]


def send_document(chat_id, pdf_bytes, filename, caption):
	"""Send a PDF to a GOWA chat. Uses multipart file upload.

	Returns (response_dict, error_str).
	"""
	# Sanitize filename: GOWA/Frappe filenames may contain slashes (e.g. GC/000003/26-27.pdf).
	safe_name = (filename or "document.pdf").replace("/", "-").replace("\\", "-")
	files = {"file": (safe_name, pdf_bytes, "application/pdf")}
	data = {"phone": chat_id.replace("@c.us", ""), "caption": caption}
	resp, err = request("/send/file", method="POST", data=data, files=files)
	if err:
		return None, err
	return resp, None


def qr_code_png(qr_string):
	"""Generate a base64 PNG data-URI from a raw WhatsApp QR string."""
	if not qr_string:
		return None
	img = qrcode.make(qr_string)
	buf = io.BytesIO()
	img.save(buf, format="PNG")
	b64 = base64.b64encode(buf.getvalue()).decode("ascii")
	return "data:image/png;base64," + b64
