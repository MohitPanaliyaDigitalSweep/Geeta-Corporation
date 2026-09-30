import json

import frappe

no_cache = 1


def _default_sales_person():
    """Best-effort default Sales Person for the logged-in user.

    Resolution order:
    1. A Sales Person whose name matches the session user's name/full_name.
    2. The first enabled, non-group Sales Person (alphabetical).
    """
    user = frappe.session.user
    candidates = frappe.get_all(
        "Sales Person",
        filters={"is_group": 0, "enabled": 1},
        fields=["name", "sales_person_name"],
        order_by="sales_person_name asc",
    )
    if not candidates:
        return ""

    full_name = ""
    if user:
        full_name = frappe.db.get_value("User", user, "full_name") or ""

    user_l = user.lower()
    full_l = (full_name or "").lower()
    for c in candidates:
        hay = ((c.sales_person_name or "") or c.name).lower()
        if user_l and user_l in hay:
            return c.sales_person_name or c.name
        if full_l and full_l in hay:
            return c.sales_person_name or c.name

    first = candidates[0]
    return first.sales_person_name or first.name


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.redirect("/login")

    context.csrf_token = frappe.sessions.get_csrf_token()
    context.site_name = frappe.local.site
    context.username = frappe.session.user

    companies = frappe.get_all(
        "Company", fields=["name"], limit_page_length=100, order_by="name asc"
    )
    context.companies = [c.get("name") for c in companies] or []
    context.companies_json = json.dumps(context.companies)

    context.default_sales_person = _default_sales_person()
    context.default_sales_person_json = json.dumps(context.default_sales_person)

    return context