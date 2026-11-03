"""WhatsApp session lifecycle for the GOWA gateway.

Drives pairing from the Fast Entry UI: show a live QR, poll the connection state,
restart a dead session, request a phone-number pairing code as an alternative to
scanning, and unlink the device again.

OpenWA (api/openwa.py) is kept in the repo for future reference but is no longer
the active transport — GOWA replaces it.
"""

import base64
import io

import frappe
import qrcode
from frappe import _

from fast_entry_app.api import gowa as openwa  # GOWA replaces OpenWA; keep alias for minimal diff

# GOWA device states we care about, mapped to a UI-friendly status.
# `logged_in` means a number is linked and messages can be sent.
CONNECTED_STATES = ("logged_in", "connected", "open")


def _require_settings():
	"""Raise a user-facing error when the WhatsApp integration is not usable yet."""
	openwa.wa_settings()
	if not openwa.base_url():
		frappe.throw(_("Set the GOWA base URL in Fast Entry Settings."))
	if not openwa.device_id():
		frappe.throw(_("Set the GOWA device ID in Fast Entry Settings."))
	if not openwa.username() or not openwa.password():
		frappe.throw(_("Set the GOWA username and password in Fast Entry Settings."))


@frappe.whitelist()
def get_session_status():
	"""Live connection state for the configured GOWA device."""

	openwa.require_whatsapp_role()

	openwa.wa_settings()
	if not (openwa.base_url() and openwa.device_id() and openwa.username() and openwa.password()):
		return {
			"ok": False,
			"configured": False,
			"message": openwa._config_error(),
			"base_url": openwa.base_url(),
			"session_id": openwa.device_id(),
		}

	info, error = openwa.request("/devices/{device}")
	if error:
		return {
			"ok": False,
			"configured": True,
			"message": _("Cannot reach the GOWA gateway: {0}").format(error),
			"base_url": openwa.base_url(),
			"session_id": openwa.device_id(),
		}

	res = (info or {}).get("results") or info or {}
	status = res.get("state") or (info or {}).get("status") or "unknown"
	phone = res.get("jid") or res.get("phone")
	if phone and "@" in str(phone):
		phone = str(phone).split("@")[0]
	return {
		"ok": True,
		"configured": True,
		"base_url": openwa.base_url(),
		"session_id": openwa.device_id(),
		"name": res.get("display_name") or res.get("name"),
		"status": status,
		"phone": phone,
		"connected": status in CONNECTED_STATES or bool(phone),
		"qr_ready": status not in CONNECTED_STATES,
		"engine_loaded": True,
		"connected_at": res.get("created_at"),
		"last_error": None,
		"restriction": None,
	}


@frappe.whitelist()
def get_session_qr():
	"""Return a data-URI PNG of the current pairing QR.

	GOWA returns raw QR strings; we render them as PNG via the qrcode library.
	"""

	openwa.require_whatsapp_role()

	_require_settings()
	res, error = openwa.request("/devices/{device}/login", timeout=20)
	if error:
		return {"ok": False, "qr": None, "message": error}

	payload = None
	r = (res or {}).get("results") or res or {}
	qr_codes = r.get("qr_codes") or r.get("qr") or r.get("qrCode")
	if isinstance(qr_codes, list) and qr_codes:
		payload = qr_codes[0]
	elif isinstance(qr_codes, str) and qr_codes:
		payload = qr_codes
	# Some GOWA versions return a qr_link (URL to a PNG).
	qr_link = r.get("qr_link")
	if not payload and qr_link:
		try:
			img_resp = openwa.request.__wrapped__ if hasattr(openwa.request, "__wrapped__") else None
		except Exception:
			pass
		# Fetch the image and convert to data-URI.
		try:
			import urllib.request
			with urllib.request.urlopen(qr_link, timeout=20) as resp:
				b64 = base64.b64encode(resp.read()).decode("ascii")
				return {"ok": True, "qr": "data:image/png;base64," + b64}
		except Exception as e:
			return {"ok": False, "qr": None, "message": str(e)}

	if not payload:
		# Already linked or stopped.
		status = r.get("state") or r.get("status") or ""
		if status in CONNECTED_STATES:
			return {"ok": False, "qr": None, "message": _("Already linked. No QR to scan.")}
		return {"ok": False, "qr": None, "message": _("No QR available. The session may already be linked or stopped.")}

	# Render the raw QR string as a PNG data-URI.
	try:
		img = qrcode.make(payload)
		buf = io.BytesIO()
		img.save(buf, format="PNG")
		b64 = base64.b64encode(buf.getvalue()).decode("ascii")
		return {"ok": True, "qr": "data:image/png;base64," + b64}
	except Exception as e:
		return {"ok": False, "qr": None, "message": str(e)}


@frappe.whitelist()
def start_session():
	"""Reconnect the device so it can be paired / send."""

	openwa.require_whatsapp_role()

	_require_settings()
	res, error = openwa.request("/devices/{device}/reconnect", method="POST", data={}, timeout=60)
	if error:
		# Reconnect may not be needed; try login instead.
		res2, error2 = openwa.request("/devices/{device}/login", timeout=20)
		if error2:
			return {"ok": False, "message": error2}
		return {"ok": True, "message": _("Session started. It may take a few seconds to show a QR.")}
	return {"ok": True, "message": _("Session reconnected.")}


@frappe.whitelist()
def stop_session():
	"""GOWA has no explicit stop; return a friendly no-op."""
	openwa.require_whatsapp_role()
	return {"ok": True, "message": _("GOWA has no stop command; the device stays connected.")}


@frappe.whitelist()
def logout_session():
	"""Unlink this device from WhatsApp and wipe stored credentials."""

	openwa.require_whatsapp_role()

	_require_settings()
	res, error = openwa.request("/devices/{device}/logout", method="POST", data={}, timeout=60)
	if error:
		return {"ok": False, "message": error}
	return {
		"ok": True,
		"message": _("Device unlinked. Scan a QR to link a number again."),
	}


@frappe.whitelist()
def request_pairing_code(phone_number=None):
	"""Request an 8-character pairing code as an alternative to scanning a QR.

	Phone number must be digits only in international format (country code + number),
	e.g. 919876543210.
	"""

	openwa.require_whatsapp_role()

	_require_settings()
	digits = frappe.utils.cstr(phone_number or "").strip()
	digits = "".join(ch for ch in digits if ch.isdigit())
	if len(digits) < 6 or len(digits) > 15:
		frappe.throw(
			_("Enter the phone number in international format, digits only (6-15 digits), e.g. 919876543210.")
		)
	res, error = openwa.request(
		"/devices/{device}/login/code?phone={0}".format(digits),
		method="POST",
		timeout=60,
	)
	if error:
		return {"ok": False, "message": error}
	return {
		"ok": True,
		"pairing_code": (res or {}).get("pairing_code") or (res or {}).get("code"),
		"status": (res or {}).get("status"),
		"message": _("Pairing code generated. Enter it in WhatsApp > Settings > Linked devices."),
	}
