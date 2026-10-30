import frappe
from frappe import _


@frappe.whitelist()
def get_party_bills_summary(company, party_type="Customer", search=""):
    from fast_entry_app.api.party_bills import get_party_bills_summary as _get
    return _get(company=company, party_type=party_type, search=search)


@frappe.whitelist()
def get_party_overdue_summary(company, party_type="Customer"):
    from fast_entry_app.api.party_bills import get_party_overdue_summary as _get
    return _get(company=company, party_type=party_type)