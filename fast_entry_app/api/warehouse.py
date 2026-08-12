import frappe


@frappe.whitelist()
def search_warehouses(search=None, company=None, limit=20):
    """Search warehouses by name."""
    limit = int(limit)
    filters = {}
    or_filters = []

    if search:
        or_filters = [
            ["warehouse_name", "like", f"%{search}%"],
            ["name", "like", f"%{search}%"],
        ]

    if company:
        filters["company"] = company

    warehouses = frappe.get_list(
        "Warehouse",
        filters=filters,
        or_filters=or_filters,
        fields=["name", "warehouse_name", "company"],
        limit_page_length=limit,
        order_by="name asc",
    )
    return warehouses
