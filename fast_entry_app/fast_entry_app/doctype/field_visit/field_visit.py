import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate, nowtime


class FieldVisit(Document):
    def validate(self):
        if not self.employee:
            frappe.throw(_("Employee is required"))
        if not self.visit_date:
            self.visit_date = nowdate()
        if not self.visit_time:
            self.visit_time = nowtime()
        # Sync lat/long from geolocation if available
        if self.geolocation and not self.latitude:
            try:
                import json
                geo = json.loads(self.geolocation) if isinstance(self.geolocation, str) else self.geolocation
                if isinstance(geo, dict):
                    self.latitude = geo.get("latitude") or geo.get("lat")
                    self.longitude = geo.get("longitude") or geo.get("lng")
            except Exception:
                pass

    def before_insert(self):
        if not self.company:
            self.company = frappe.db.get_value("Employee", self.employee, "company")
        if not self.visit_date:
            self.visit_date = nowdate()
        if not self.visit_time:
            self.visit_time = nowtime()