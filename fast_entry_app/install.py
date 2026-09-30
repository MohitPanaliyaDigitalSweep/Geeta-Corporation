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
"""


def after_install():
	from fast_entry_app.setup_custom_fields import execute

	execute()
