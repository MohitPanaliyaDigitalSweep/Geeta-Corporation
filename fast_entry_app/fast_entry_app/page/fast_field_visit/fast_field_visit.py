import frappe
from frappe import _


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