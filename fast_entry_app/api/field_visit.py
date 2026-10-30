import frappe
from frappe import _
from frappe.utils import nowdate, nowtime


@frappe.whitelist()
def create_field_visit(data):
    """Create a Field Visit record with location, photo, and remarks."""
    if isinstance(data, str):
        import json
        data = json.loads(data)

    doc = frappe.new_doc("Field Visit")
    doc.employee = data.get("employee")
    doc.company = data.get("company") or frappe.db.get_value("Employee", data.get("employee"), "company")
    doc.visit_date = data.get("visit_date") or nowdate()
    doc.visit_time = data.get("visit_time") or nowtime()
    doc.party_type = data.get("party_type") or "None"
    doc.party = data.get("party")
    doc.party_name = data.get("party_name")
    doc.visit_type = data.get("visit_type") or "Customer Visit"
    doc.geolocation = data.get("geolocation")
    doc.latitude = data.get("latitude")
    doc.longitude = data.get("longitude")
    doc.photo = data.get("photo")
    doc.remarks = data.get("remarks")
    doc.status = data.get("status") or "Draft"

    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_field_visits(employee=None, company=None, from_date=None, to_date=None, limit=50):
    """Get field visits for a user/company."""
    filters = {}
    if employee:
        filters["employee"] = employee
    if company:
        filters["company"] = company
    if from_date:
        filters["visit_date"] = [">=", from_date]
    if to_date:
        filters["visit_date"] = ["<=", to_date]

    visits = frappe.get_all(
        "Field Visit",
        filters=filters,
        fields=["name", "employee", "employee_name", "company", "visit_date", "visit_time",
                "party_type", "party", "party_name", "visit_type", "status",
                "latitude", "longitude", "photo", "remarks"],
        order_by="visit_date desc, visit_time desc",
        limit_page_length=int(limit),
    )
    return visits


@frappe.whitelist()
def get_live_locations(company=None):
    """Get latest location for each employee (from Field Visit or Employee Checkin)."""
    # Get latest field visit per employee
    locations = []
    filters = {}
    if company:
        filters["company"] = company

    # Get the most recent visit per employee
    employees = frappe.get_all("Employee", filters={"status": "Active"}, fields=["name", "employee_name", "company"])
    for emp in employees:
        if company and emp.company != company:
            continue
        # Latest field visit
        visit = frappe.db.get_value(
            "Field Visit",
            {"employee": emp.name},
            ["latitude", "longitude", "visit_date", "visit_time", "party_name", "remarks"],
            order_by="visit_date desc, visit_time desc",
            as_dict=True,
        )
        # Fallback to Employee Checkin
        if not visit or not visit.get("latitude"):
            checkin = frappe.db.get_value(
                "Employee Checkin",
                {"employee": emp.name},
                ["latitude", "longitude", "time"],
                order_by="time desc",
                as_dict=True,
            )
            if checkin and checkin.get("latitude"):
                visit = {
                    "latitude": checkin.get("latitude"),
                    "longitude": checkin.get("longitude"),
                    "visit_date": checkin.get("time").date() if checkin.get("time") else None,
                    "visit_time": checkin.get("time").time() if checkin.get("time") else None,
                    "party_name": None,
                    "remarks": None,
                }

        if visit and visit.get("latitude") and visit.get("longitude"):
            locations.append({
                "employee": emp.name,
                "employee_name": emp.employee_name,
                "company": emp.company,
                "latitude": visit.get("latitude"),
                "longitude": visit.get("longitude"),
                "visit_date": str(visit.get("visit_date")) if visit.get("visit_date") else None,
                "visit_time": str(visit.get("visit_time")) if visit.get("visit_time") else None,
                "party_name": visit.get("party_name"),
                "remarks": visit.get("remarks"),
            })

    return locations