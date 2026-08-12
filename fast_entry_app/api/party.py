import frappe
from frappe import _


@frappe.whitelist()
def search_suppliers(search=None, company=None, limit=20):
    """Search suppliers by name or code. If company selected, show company suppliers first, then all."""
    limit = int(limit)
    like = f"%{search}%" if search else "%%"

    suppliers = []

    if company:
        gstin_expr = "s.gstin" if frappe.db.has_column("Supplier", "gstin") else "'' as gstin"
        sql = f"""
            SELECT DISTINCT pi.supplier as name, s.supplier_name, {gstin_expr}
            FROM `tabPurchase Invoice` pi
            INNER JOIN `tabSupplier` s ON s.name = pi.supplier
            WHERE pi.docstatus = 1 AND pi.company = %s
            AND (pi.supplier LIKE %s OR s.supplier_name LIKE %s)
            ORDER BY s.supplier_name ASC
            LIMIT %s
        """
        suppliers = frappe.db.sql(sql, (company, like, like, limit), as_dict=True)

    if not suppliers:
        or_filters = []
        if search:
            or_filters = [
                ["name", "like", f"%{search}%"],
                ["supplier_name", "like", f"%{search}%"],
            ]
        fields = ["name", "supplier_name"]
        if frappe.db.has_column("Supplier", "gstin"):
            fields.append("gstin")
        suppliers = frappe.get_list(
            "Supplier",
            filters={},
            or_filters=or_filters,
            fields=fields,
            limit_page_length=limit,
            order_by="name asc",
        )
    return suppliers


@frappe.whitelist()
def get_supplier_details(supplier, company=None):
    """Get supplier details including outstanding balance."""
    if not supplier:
        frappe.throw(_("Supplier is required"))

    supplier_doc = frappe.get_doc("Supplier", supplier)
    result = {
        "supplier_name": supplier_doc.supplier_name,
        "gstin": getattr(supplier_doc, "gstin", "") or "",
        "supplier_group": supplier_doc.supplier_group,
        "default_currency": supplier_doc.default_currency or "INR",
    }

    # Outstanding balance
    if company:
        outstanding = frappe.db.sql(
            """
            SELECT SUM(debit) - SUM(credit) as balance
            FROM `tabGL Entry`
            WHERE party_type = 'Supplier' AND party = %s AND company = %s
            """,
            (supplier, company),
            as_dict=True,
        )
        if outstanding and outstanding[0].balance:
            bal = abs(outstanding[0].balance)
            result["outstanding"] = bal
            result["balance_type"] = "Cr" if outstanding[0].balance > 0 else "Dr"
        else:
            result["outstanding"] = 0
            result["balance_type"] = "Cr"
    else:
        result["outstanding"] = 0
        result["balance_type"] = "Cr"

    # Credit days
    credit_days = frappe.db.get_value(
        "Supplier Group", supplier_doc.supplier_group, "payment_terms"
    )
    result["credit_days"] = credit_days or 0

    return result


@frappe.whitelist()
def search_customers(search=None, company=None, limit=20):
    """Search customers by name or code. If company selected, show company customers first, then all."""
    limit = int(limit)
    like = f"%{search}%" if search else "%%"

    customers = []

    if company:
        gstin_expr = "c.gstin" if frappe.db.has_column("Customer", "gstin") else "'' as gstin"
        sql = f"""
            SELECT DISTINCT si.customer as name, c.customer_name, {gstin_expr}
            FROM `tabSales Invoice` si
            INNER JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.docstatus = 1 AND si.company = %s
            AND (si.customer LIKE %s OR c.customer_name LIKE %s)
            ORDER BY c.customer_name ASC
            LIMIT %s
        """
        customers = frappe.db.sql(sql, (company, like, like, limit), as_dict=True)

    if not customers:
        or_filters = []
        if search:
            or_filters = [
                ["name", "like", f"%{search}%"],
                ["customer_name", "like", f"%{search}%"],
            ]
        fields = ["name", "customer_name"]
        if frappe.db.has_column("Customer", "gstin"):
            fields.append("gstin")
        customers = frappe.get_list(
            "Customer",
            filters={},
            or_filters=or_filters,
            fields=fields,
            limit_page_length=limit,
            order_by="name asc",
        )
    return customers


@frappe.whitelist()
def get_customer_details(customer, company=None):
    """Get customer details including outstanding balance."""
    if not customer:
        frappe.throw(_("Customer is required"))

    customer_doc = frappe.get_doc("Customer", customer)
    result = {
        "customer_name": customer_doc.customer_name,
        "gstin": getattr(customer_doc, "gstin", "") or "",
        "customer_group": customer_doc.customer_group,
        "default_currency": customer_doc.default_currency or "INR",
    }

    # Outstanding balance
    if company:
        outstanding = frappe.db.sql(
            """
            SELECT SUM(debit) - SUM(credit) as balance
            FROM `tabGL Entry`
            WHERE party_type = 'Customer' AND party = %s AND company = %s
            """,
            (customer, company),
            as_dict=True,
        )
        if outstanding and outstanding[0].balance:
            bal = abs(outstanding[0].balance)
            result["outstanding"] = bal
            result["balance_type"] = "Dr" if outstanding[0].balance > 0 else "Cr"
        else:
            result["outstanding"] = 0
            result["balance_type"] = "Dr"
    else:
        result["outstanding"] = 0
        result["balance_type"] = "Dr"

    return result


@frappe.whitelist()
def get_party_balance(party, party_type, company):
    """Get outstanding balance for a party."""
    if not party or not party_type or not company:
        return {"outstanding": 0, "balance_type": "Cr"}

    outstanding = frappe.db.sql(
        """
        SELECT SUM(debit) - SUM(credit) as balance
        FROM `tabGL Entry`
        WHERE party_type = %s AND party = %s AND company = %s
        """,
        (party_type, party, company),
        as_dict=True,
    )

    if outstanding and outstanding[0].balance:
        bal = abs(outstanding[0].balance)
        balance_type = "Cr" if outstanding[0].balance > 0 else "Dr"
        return {"outstanding": bal, "balance_type": balance_type}

    return {"outstanding": 0, "balance_type": "Cr"}
