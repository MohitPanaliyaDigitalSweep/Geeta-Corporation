import frappe
from frappe import _
from frappe.utils import now_datetime


@frappe.whitelist()
def ping_location(latitude, longitude, employee=None, accuracy=None):
    """Record a location ping for an employee (creates an Employee Checkin)."""
    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        frappe.throw(_("No Employee linked to this user"))

    # Check consent (custom field or cache)
    consent = None
    if frappe.db.has_column("Employee", "location_tracking_consent"):
        consent = frappe.db.get_value("Employee", employee, "location_tracking_consent")
    if consent is None:
        consent = frappe.cache().get_value(f"location_consent:{employee}")
    if consent is not None and not consent:
        frappe.throw(_("Location tracking consent not granted for this employee"))

    checkin = frappe.new_doc("Employee Checkin")
    checkin.employee = employee
    checkin.log_type = "IN"
    checkin.time = now_datetime()
    checkin.latitude = float(latitude)
    checkin.longitude = float(longitude)
    checkin.device_id = "fast_entry_app"
    if accuracy:
        checkin.geolocation = '{"type":"Feature","geometry":{"type":"Point","coordinates":[' + str(longitude) + ',' + str(latitude) + ']},"properties":{"accuracy":' + str(accuracy) + '}}'
    checkin.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "ok", "name": checkin.name}


@frappe.whitelist()
def get_tracking_consent(employee=None):
    """Check if employee has consented to location tracking."""
    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        return {"consented": False, "employee": None}
    # Store consent in a simple custom field or use a separate setting
    # For now, default to True (can be toggled via Employee form later)
    return {"consented": True, "employee": employee}


@frappe.whitelist()
def set_tracking_consent(consented, employee=None):
    """Set location tracking consent for an employee."""
    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        frappe.throw(_("No Employee linked to this user"))
    # Store in cache for now (can be persisted to Employee custom field later)
    frappe.cache().set_value(f"location_consent:{employee}", 1 if consented else 0)
    return {"status": "ok"}