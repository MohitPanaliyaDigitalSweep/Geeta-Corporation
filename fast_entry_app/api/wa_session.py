"""WhatsApp session lifecycle for the OpenWA gateway.

Lets the Fast Entry app drive pairing from its own UI: show a live QR, poll the
connection state, restart a dead session, request a phone-number pairing code as an
alternative to scanning, and unlink the device again.
"""

import frappe
from frappe import _

from fast_entry_app.api import openwa

# Gateway session states we care about, mapped to a UI-friendly status.
# `connected` means a number is linked and messages can be sent.
CONNECTED_STATES = ("connected", "authenticated", "ready")


def _require_settings():
	"""Raise a user-facing error when the WhatsApp integration is not usable yet."""
	openwa.wa_settings()
	if not openwa.base_url():
		frappe.throw(_("Set the OpenWA base URL in Fast Entry Settings."))
	if not openwa.session_id():
		frappe.throw(_("Set the OpenWA session ID in Fast Entry Settings."))
	if not openwa.api_key():
		frappe.throw(_("Set the OpenWA API key in Fast Entry Settings."))


@frappe.whitelist()
def get_session_status():
	"""Live connection state for the configured OpenWA session.

	Returns a normalized dict; `ok` is False when the gateway itself is unreachable or
	rejects the credentials, with the reason in `message`.
	"""

	openwa.require_whatsapp_role()

	openwa.wa_settings()
	if not (openwa.base_url() and openwa.session_id() and openwa.api_key()):
		return {
			"ok": False,
			"configured": False,
			"message": openwa._config_error(),
			"base_url": openwa.base_url(),
			"session_id": openwa.session_id(),
		}

	info, error = openwa.request("/api/sessions/{session}")
	if error:
		return {
			"ok": False,
			"configured": True,
			"message": _("Cannot reach the OpenWA gateway: {0}").format(error),
			"base_url": openwa.base_url(),
			"session_id": openwa.session_id(),
		}

	status = (info or {}).get("status") or "unknown"
	phone = (info or {}).get("phone")
	return {
		"ok": True,
		"configured": True,
		"base_url": openwa.base_url(),
		"session_id": openwa.session_id(),
		"name": (info or {}).get("name"),
		"status": status,
		"phone": phone,
		"connected": status in CONNECTED_STATES or bool(phone),
		# A live QR only exists while the session is waiting to be paired.
		"qr_ready": status == "qr_ready",
		"engine_loaded": bool((info or {}).get("engineLoaded")),
		"connected_at": (info or {}).get("connectedAt"),
		"last_error": (info or {}).get("lastError"),
		"restriction": (info or {}).get("restriction"),
	}


@frappe.whitelist()
def get_session_qr():
	"""Return a data-URI PNG of the current pairing QR.

	The QR rotates every ~20-60s, so callers should re-fetch rather than cache it.
	Returns `qr` as None when there is nothing to scan (already linked, or stopped).
	"""

	openwa.require_whatsapp_role()

	_require_settings()
	res, error = openwa.request("/api/sessions/{session}/qr", timeout=20)
	if error:
		return {"ok": False, "qr": None, "message": error}

	payload = (res or {}).get("qr") or (res or {}).get("qrCode") or (res or {}).get("data") or ""
	if not payload:
		return {
			"ok": False,
			"qr": None,
			"message": _("No QR available. The session may already be linked or stopped."),
		}
	if not payload.startswith("data:image"):
		payload = "data:image/png;base64," + payload
	return {"ok": True, "qr": payload}


@frappe.whitelist()
def start_session():
	"""Start (or wake) the gateway session engine so it can be paired / send."""

	openwa.require_whatsapp_role()

	_require_settings()
	res, error = openwa.request("/api/sessions/{session}/start", method="POST", data={}, timeout=60)
	if error:
		return {"ok": False, "message": error}
	return {"ok": True, "message": _("Session started. It may take a few seconds to show a QR.")}


@frappe.whitelist()
def stop_session():
	"""Stop the session engine. Pairing survives a stop; a restart reuses stored credentials."""

	openwa.require_whatsapp_role()

	_require_settings()
	res, error = openwa.request("/api/sessions/{session}/stop", method="POST", data={}, timeout=60)
	if error:
		return {"ok": False, "message": error}
	return {"ok": True, "message": _("Session stopped.")}


@frappe.whitelist()
def logout_session():
	"""Unlink this device from WhatsApp and wipe stored credentials (session returns to QR)."""

	openwa.require_whatsapp_role()

	_require_settings()
	res, error = openwa.request("/api/sessions/{session}/logout", method="POST", data={}, timeout=60)
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
	e.g. 919876543210. The user then enters the code in
	WhatsApp > Settings > Linked devices > Link with phone number.
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
		"/api/sessions/{session}/pairing-code",
		method="POST",
		data={"phoneNumber": digits},
		timeout=60,
	)
	if error:
		return {"ok": False, "message": error}
	return {
		"ok": True,
		"pairing_code": (res or {}).get("pairingCode") or (res or {}).get("pairing_code"),
		"status": (res or {}).get("status"),
		"message": _("Pairing code generated. Enter it in WhatsApp > Settings > Linked devices."),
	}
