import frappe
import json


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login"
        raise frappe.Redirect
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.site_name = frappe.local.site
    context.username = frappe.session.user
    companies = frappe.get_all("Company", pluck="name")
    context.companies_json = json.dumps(companies)
    # Default employee for the logged-in user
    emp = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    context.default_employee = emp or ""