"""Gateway health check for the GOWA WhatsApp bridge.

Separates the layers so an operator can see *where* a problem is, rather than just
"send failed":

    1. settings      - is the integration enabled and fully filled in?
    2. gateway       - is the HTTP service up and answering /health?
    3. auth          - are the Basic Auth credentials accepted?
    4. device        - does the configured device exist, and is it logged in?
    5. pairing       - is a number linked, so sends can actually succeed?
"""

import time
import urllib.error
import urllib.request

import frappe
import requests
from frappe import _

from fast_entry_app.api import gowa as openwa  # GOWA replaces OpenWA; keep alias
from fast_entry_app.api.wa_session import CONNECTED_STATES

HEALTH_TIMEOUT = 6

LEVEL_OK = "ok"
LEVEL_WARN = "warn"
LEVEL_ERROR = "error"


def _ms(started):
	return int((time.monotonic() - started) * 1000)


def _check(name, level, message, **extra):
	row = {"name": name, "level": level, "message": message}
	row.update(extra)
	return row


def _probe_health(base_url):
	"""GET /health without auth. Returns (ok, ms, detail)."""
	started = time.monotonic()
	url = base_url.rstrip("/") + "/health"
	try:
		resp = requests.get(url, timeout=HEALTH_TIMEOUT)
		detail = (resp.text or "").strip()[:120] or "HTTP {0}".format(resp.status_code)
		return True, _ms(started), detail
	except requests.exceptions.ConnectionError as e:
		return False, _ms(started), str(e)[:160]
	except requests.exceptions.Timeout as e:
		return False, _ms(started), "Timed out: {0}".format(str(e)[:160])
	except Exception as e:
		return False, _ms(started), str(e)[:160]


@frappe.whitelist()
def check_gateway():
	"""Run the full connectivity check and return a step-by-step report."""
	openwa.require_whatsapp_role()

	checks = []
	openwa.wa_settings()
	base_url = openwa.base_url()
	device_id = openwa.device_id()
	username = openwa.username()
	password = openwa.password()
	enabled = bool(openwa.wa_settings().get("whatsapp_enabled"))

	# --- 1. settings -------------------------------------------------------
	missing = [
		label
		for label, value in (
			("GOWA base URL", base_url),
			("GOWA device ID", device_id),
			("GOWA username", username),
			("GOWA password", password),
		)
		if not value
	]
	if missing:
		checks.append(
			_check(
				_("Settings"),
				LEVEL_ERROR,
				_("Missing: {0}. Set these in Fast Entry Settings.").format(", ".join(missing)),
				passed=False,
			)
		)
	elif not enabled:
		checks.append(
			_check(
				_("Settings"),
				LEVEL_WARN,
				_("Everything is filled in, but WhatsApp Integration is switched off."),
				passed=True,
			)
		)
	else:
		checks.append(
			_check(
				_("Settings"),
				LEVEL_OK,
				_("WhatsApp Integration is enabled and fully configured."),
				passed=True,
			)
		)

	# --- 2. gateway reachable ---------------------------------------------
	if not base_url:
		checks.append(_check(_("Gateway reachable"), LEVEL_ERROR, _("No base URL configured."), passed=False))
		return _report(checks, False)

	up, elapsed, detail = _probe_health(base_url)
	checks.append(
		_check(
			_("Gateway reachable"),
			LEVEL_OK if up else LEVEL_ERROR,
			_("Responded on {0} in {1}ms ({2})").format(base_url, elapsed, detail)
			if up
			else _("No response from {0} ({1}). Is the gateway process running?").format(base_url, detail),
			passed=up,
			ms=elapsed,
		)
	)
	if not up:
		return _report(checks, False)

	# --- 3. auth + device -------------------------------------------------
	if not (device_id and username and password):
		checks.append(
			_check(_("Credentials accepted"), LEVEL_ERROR, _("Device ID, username and password are required."), passed=False)
		)
		return _report(checks, False)

	started = time.monotonic()
	info, error = openwa.request("/devices/{device}", timeout=HEALTH_TIMEOUT * 2)
	elapsed = _ms(started)
	if error:
		auth_bad = error.startswith(("401", "403"))
		checks.append(
			_check(
				_("Credentials accepted"),
				LEVEL_ERROR,
				_("The gateway rejected the credentials ({0}). Re-check username/password in Fast Entry Settings.").format(error)
				if auth_bad
				else error,
				passed=False,
				ms=elapsed,
			)
		)
		return _report(checks, False)

	checks.append(
		_check(
			_("Credentials accepted"),
			LEVEL_OK,
			_("Credentials accepted ({0}ms).").format(elapsed),
			passed=True,
			ms=elapsed,
		)
	)

	res = (info or {}).get("results") or info or {}
	status = res.get("state") or (info or {}).get("status") or "unknown"
	checks.append(
		_check(
			_("Device reachable"),
			LEVEL_OK,
			_("Device \"{0}\" found - state: {1}.").format(device_id, status),
			passed=True,
		)
	)

	# --- 4. pairing -------------------------------------------------------
	phone = res.get("jid")
	if phone and "@" in str(phone):
		phone = str(phone).split("@")[0]
	linked = status in CONNECTED_STATES or bool(phone)

	if linked:
		checks.append(
			_check(
				_("Number linked"),
				LEVEL_OK,
				_("Linked as +{0}. Sending is ready.").format(phone) if phone
				else _("Linked (state: {0}).").format(status),
				passed=True,
			)
		)
	else:
		checks.append(
			_check(
				_("Number linked"),
				LEVEL_WARN,
				_("No number linked yet. Scan the QR in the Connection card, or use a pairing code."),
				passed=False,
			)
		)

	return _report(checks, linked)


def _report(checks, all_ok):
	return {
		"ok": all_ok,
		"checks": checks,
		"failed": [c for c in checks if not c.get("passed")],
		"summary": _(
			"Gateway is healthy and ready to send."
		)
		if all_ok
		else _("Gateway needs attention - see the failed checks below."),
	}
