"""Run after this app is installed on a site.

Frappe marks every patch in ``patches.txt`` as already completed during
``install-app`` (``frappe.installer.set_all_patches_as_completed``), so patches
never actually execute on a fresh install. Without this hook our custom fields
and property setters would only be created by the fixture import, and the
Property Setters (which cannot be fixtures, because their ``doc_type`` link
would fail validation on a site without ERPNext) would never be created at all.

Safe to run more than once, and safe on a site where ERPNext is not installed
yet: :func:`setup_custom_fields.execute` skips doctypes that do not exist, in
which case ``after_migrate`` picks things up later.

:func:`setup_gst_sandbox` additionally puts India Compliance's GST API in
sandbox mode on sites that have no Company GSTIN yet (see its docstring).
"""

import frappe


def after_install():
	from fast_entry_app.setup_custom_fields import execute

	execute()
	setup_gst_sandbox()


def setup_gst_sandbox():
	"""Put India Compliance's GST API in sandbox mode on fresh installs.

	India Compliance only auto-enables ``sandbox_mode`` on sites running in
	``frappe.conf.developer_mode``. For everyone else the flag is checked off,
	so fresh benches that want to exercise e-Invoice / e-Waybill (without an
	NIC login or GSP credentials) had to tick it by hand.

	Scope guard: a site where ANY Company already has a ``gstin`` is treated
	as real data and is NEVER switched to sandbox automatically.

	Idempotent: no save when the settings are already correct. Runs from both
	the ``after_install`` and ``after_migrate`` hooks, so a site that adds
	india_compliance later (or clears its companies' GSTINs) converges on the
	next ``bench migrate``. Any failure is logged, never thrown, so it cannot
	break an install/migrate.
	"""
	try:
		if "india_compliance" not in frappe.get_installed_apps():
			return

		if not frappe.db.exists("GST Settings", "GST Settings"):
			return

		if frappe.db.get_all("Company", filters={"gstin": ["is", "set"]}, limit=1):
			return

		settings = frappe.get_doc("GST Settings")
		api_secret = settings.get_password("api_secret", raise_exception=False) or ""

		if settings.sandbox_mode != 1 or api_secret != "test_sandbox_api_key":
			settings.flags.ignore_permissions = True
			settings.sandbox_mode = 1
			settings.api_secret = "test_sandbox_api_key"
			settings.save()

	except Exception:
		frappe.log_error(title="fast_entry_app: failed to enable GST sandbox")
