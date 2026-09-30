"""Gateway health check for the OpenWA WhatsApp bridge.

Separates the layers so an operator can see *where* a problem is, rather than just
"send failed":

    1. settings      - is the integration enabled and fully filled in?
    2. gateway       - is the HTTP service up and answering /api/health?
    3. auth          - is the API key accepted (operator role)?
    4. session       - does the configured session exist, and is its engine loaded?
    5. pairing       - is a number linked, so sends can actually succeed?
"""

import time
import urllib.error
import urllib.request

import frappe
from frappe import _

from fast_entry_app.api import openwa
from fast_entry_app.api.wa_session import CONNECTED_STATES

# Keep the probe short: this runs on a button click and must feel instant.
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
	"""GET /api/health without auth. Returns (ok, ms, detail)."""
	started = time.monotonic()
	url = base_url.rstrip("/") + "/api/health"
	try:
		with urllib.request.urlopen(url, timeout=HEALTH_TIMEOUT) as resp:
			raw = resp.read().decode("utf-8", "replace")
			# Health may be JSON or plain text; report whichever, trimmed.
			detail = raw.strip()[:120] or "HTTP {0}".format(resp.status)
			return True, _ms(started), detail
	except urllib.error.HTTPError as e:
		# A response at all proves something is listening and speaking HTTP.
		return True, _ms(started), "HTTP {0} (service is up)".format(e.code)
	except Exception as e:
		return False, _ms(started), str(e)[:160]


@frappe.whitelist()
def check_gateway():
	"""Run the full connectivity check and return a step-by-step report.

	`ok` is True only when every layer passes, i.e. sending should work right now.
	"""
	openwa.require_whatsapp_role()

	checks = []
	openwa.wa_settings()
	base_url = openwa.base_url()
	session_id = openwa.session_id()
	api_key = openwa.api_key()
	enabled = bool(openwa.wa_settings().get("whatsapp_enabled"))

	# --- 1. settings -------------------------------------------------------
	missing = [
		label
		for label, value in (
			("OpenWA base URL", base_url),
			("OpenWA session ID", session_id),
			("OpenWA API key", api_key),
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

	# --- 3+4. auth and session --------------------------------------------
	if not session_id or not api_key:
		checks.append(
			_check(_("Credentials accepted"), LEVEL_ERROR, _("Session ID and API key are required."), passed=False)
		)
		return _report(checks, False)

	started = time.monotonic()
	info, error = openwa.request("/api/sessions/{session}", timeout=HEALTH_TIMEOUT * 2)
	elapsed = _ms(started)
	if error:
		# 401/403 means the service is up but the key is wrong - a distinct fix.
		auth_bad = error.startswith(("401", "403"))
		checks.append(
			_check(
				_("Credentials accepted"),
				LEVEL_ERROR,
				_("The gateway rejected the API key ({0}). Re-check the key in Fast Entry Settings.").format(error)
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
			_("API key accepted ({0}ms).").format(elapsed),
			passed=True,
			ms=elapsed,
		)
	)

	name = (info or {}).get("name")
	status = (info or {}).get("status") or "unknown"
	checks.append(
		_check(
			_("Session reachable"),
			LEVEL_OK,
			_("Session \"{0}\" found - state: {1}.").format(name or session_id[:8], status),
			passed=True,
		)
	)

	# --- 5. engine + pairing ----------------------------------------------
	engine = bool((info or {}).get("engineLoaded"))
	checks.append(
		_check(
			_("Engine running"),
			LEVEL_OK if engine else LEVEL_WARN,
			_("Engine is loaded and can send messages.") if engine
			else _("Engine is not loaded. Restart the session to bring it up."),
			passed=engine,
		)
	)

	phone = (info or {}).get("phone")
	linked = status in CONNECTED_STATES or bool(phone)
	restriction = (info or {}).get("restriction")
	last_error = (info or {}).get("lastError")

	if restriction:
		checks.append(
			_check(
				_("Number linked"),
				LEVEL_ERROR,
				_("WhatsApp restricted this account: {0}").format(restriction),
				passed=False,
			)
		)
	elif linked:
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
		hint = (
			"Scan the QR in the Connection card above, or use a phone pairing code."
			if status == "qr_ready"
			else "Use \"Start session\" in the Connection card, then link a number."
		)
		checks.append(
			_check(_("Number linked"), LEVEL_WARN, _("No number linked yet. {0}").format(hint), passed=False)
		)

	if last_error:
		checks.append(_check(_("Last gateway error"), LEVEL_WARN, str(last_error)[:200], passed=True))

	return _report(checks, True)


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
