import frappe
from frappe import _


@frappe.whitelist()
def get_live_locations(company=None):
    """Get latest location for each active employee."""
    from fast_entry_app.api.field_visit import get_live_locations as _get
    return _get(company=company)