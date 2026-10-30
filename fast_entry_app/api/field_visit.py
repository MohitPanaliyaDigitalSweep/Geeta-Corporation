import frappe
from frappe import _
from frappe.utils import nowdate, nowtime


@frappe.whitelist()
def get_my_employee():
    """Get the Employee linked to the current logged-in user."""
    emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if emp:
        return frappe.get_value("Employee", emp, ["name", "employee_name", "company"], as_dict=True)
    return None


@frappe.whitelist()
def get_employees(company=None):
    filters = {"status": "Active"}
    if company:
        filters["company"] = company
    return frappe.get_all("Employee", filters=filters, fields=["name", "employee_name", "company"], order_by="employee_name asc")


@frappe.whitelist()
def get_customers(search, company=None, limit=20):
    if not search or len(search) < 1:
        return []
    or_filters = [["customer_name", "like", f"%{search}%"], ["name", "like", f"%{search}%"]]
    return frappe.get_all("Customer", filters={}, or_filters=or_filters, fields=["name", "customer_name"], limit_page_length=int(limit), order_by="customer_name asc")


@frappe.whitelist()
def get_suppliers(search, company=None, limit=20):
    if not search or len(search) < 1:
        return []
    or_filters = [["supplier_name", "like", f"%{search}%"], ["name", "like", f"%{search}%"]]
    return frappe.get_all("Supplier", filters={}, or_filters=or_filters, fields=["name", "supplier_name"], limit_page_length=int(limit), order_by="supplier_name asc")


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
    doc.photo = data.get("photo")  # primary photo (backward compat)
    doc.remarks = data.get("remarks")
    doc.status = data.get("status") or "Draft"

    # Handle multiple photos
    photos = data.get("photos") or []
    if isinstance(photos, str):
        import json
        try:
            photos = json.loads(photos)
        except Exception:
            photos = []
    for p in photos:
        if p:
            doc.append("photos", {"photo": p})
    # If no photos list but single photo provided, add it
    if not photos and data.get("photo"):
        doc.append("photos", {"photo": data.get("photo")})

    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_today_visit_count(employee=None):
    """Count of visits logged today by an employee."""
    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    if not employee:
        return 0
    from frappe.utils import nowdate
    count = frappe.db.count("Field Visit", filters={"employee": employee, "visit_date": nowdate()})
    return count


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
    # Attach photos from child table
    for v in visits:
        v["photos"] = frappe.get_all(
            "Field Visit Photo",
            filters={"parent": v["name"]},
            fields=["photo", "caption"],
            order_by="idx asc",
        )
        # Fall back to single photo field if no child rows
        if not v["photos"] and v.get("photo"):
            v["photos"] = [{"photo": v["photo"], "caption": ""}]
    return visits


@frappe.whitelist()
def get_customer_locations(company=None):
    """Get all customers with geolocation data."""
    filters = {}
    if company:
        filters["company"] = company
    customers = frappe.get_all(
        "Customer",
        filters=filters,
        fields=["name", "customer_name", "geolocation"],
    )
    result = []
    for c in customers:
        if not c.get("geolocation"):
            continue
        try:
            import json
            geo = json.loads(c.geolocation) if isinstance(c.geolocation, str) else c.geolocation
            if isinstance(geo, dict) and geo.get("geometry"):
                coords = geo["geometry"].get("coordinates", [])
                if len(coords) >= 2:
                    result.append({
                        "name": c.name,
                        "party_name": c.customer_name or c.name,
                        "type": "customer",
                        "latitude": coords[1],
                        "longitude": coords[0],
                    })
        except Exception:
            pass
    return result


@frappe.whitelist()
def get_supplier_locations(company=None):
    """Get all suppliers with geolocation data."""
    filters = {}
    if company:
        filters["company"] = company
    suppliers = frappe.get_all(
        "Supplier",
        filters=filters,
        fields=["name", "supplier_name", "geolocation"],
    )
    result = []
    for s in suppliers:
        if not s.get("geolocation"):
            continue
        try:
            import json
            geo = json.loads(s.geolocation) if isinstance(s.geolocation, str) else s.geolocation
            if isinstance(geo, dict) and geo.get("geometry"):
                coords = geo["geometry"].get("coordinates", [])
                if len(coords) >= 2:
                    result.append({
                        "name": s.name,
                        "party_name": s.supplier_name or s.name,
                        "type": "supplier",
                        "latitude": coords[1],
                        "longitude": coords[0],
                    })
        except Exception:
            pass
    return result


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