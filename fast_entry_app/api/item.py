import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def search_items(search, company=None, limit=20):
    """Search items by name or code, with UOM and conversion factor."""
    if not search or len(search) < 1:
        return []

    limit = int(limit)

    or_filters = [
        ["item_name", "like", f"%{search}%"],
        ["item_code", "like", f"%{search}%"],
    ]

    items = frappe.get_list(
        "Item",
        filters={},
        or_filters=or_filters,
        fields=["item_code", "item_name", "stock_uom"],
        limit_page_length=limit,
        order_by="item_name asc",
    )

    for item in items:
        uoms = frappe.get_all(
            "UOM Conversion Detail",
            filters={"parent": item.item_code},
            fields=["uom", "conversion_factor"],
        )
        item["uoms"] = uoms

    return items


@frappe.whitelist()
def get_item_details(item_code, warehouse=None, company=None):
    """Get full item details including UOM conversions, GST rate, stock, and accounts."""
    item = frappe.get_doc("Item", item_code)
    if not item:
        frappe.throw(_("Item {0} not found").format(item_code))

    result = {
        "item_code": item.item_code,
        "item_name": item.item_name,
        "stock_uom": item.stock_uom,
        "description": item.description or "",
        "hsn_code": getattr(item, "gst_hsn_code", "") or "",
        "is_stock_item": item.is_stock_item,
    }

    # UOM conversions
    uoms = []
    for uom_row in item.uoms:
        uoms.append({
            "uom": uom_row.uom,
            "conversion_factor": uom_row.conversion_factor,
        })
    result["uoms"] = uoms

    # GST rate from Item Tax Template or Company
    result["gst_rate"] = _get_item_gst_rate(item_code, company)

    # Warehouse and stock
    if warehouse:
        result["warehouse"] = warehouse
        bin_data = frappe.db.get_value(
            "Bin",
            {"item_code": item_code, "warehouse": warehouse},
            ["actual_qty", "reserved_qty", "projected_qty"],
            as_dict=True,
        )
        if bin_data:
            result["actual_qty"] = bin_data.actual_qty or 0
            result["reserved_qty"] = bin_data.reserved_qty or 0
            result["projected_qty"] = bin_data.projected_qty or 0
        else:
            result["actual_qty"] = 0
            result["reserved_qty"] = 0
            result["projected_qty"] = 0

    # Default warehouse from Item or Company
    if not warehouse:
        default_wh = _get_default_warehouse(item_code, company)
        if default_wh:
            result["warehouse"] = default_wh

    # Expense account (for Purchase Invoice)
    if company:
        result["expense_account"] = _get_expense_account(item_code, company)
        result["income_account"] = _get_income_account(item_code, company)

    # Default rate from Price List
    if company:
        result["rate"] = _get_item_rate(item_code, company)

    return result


@frappe.whitelist()
def get_stock(item_code, company):
    """Get stock across all warehouses for an item."""
    if not item_code or not company:
        return []

    stock = frappe.db.sql(
        """
        SELECT warehouse, actual_qty, reserved_qty, projected_qty, stock_value
        FROM `tabBin`
        WHERE item_code = %s AND actual_qty != 0
        ORDER BY warehouse
        """,
        (item_code,),
        as_dict=True,
    )
    return stock


@frappe.whitelist()
def get_item_stock(item_code, company, warehouse=None):
    """Get stock for an item: current warehouse qty + all warehouses breakdown.

    Returns:
        current_stock: dict with actual_qty, reserved_qty, projected_qty for the specified warehouse
        warehouse_stock: list of warehouses of the company where this item has stock
        total_actual_qty: sum of actual_qty across all warehouses of the company
    """
    if not item_code or not company:
        return {"current_stock": {}, "warehouse_stock": [], "total_actual_qty": 0}

    current_stock = {"actual_qty": 0, "reserved_qty": 0, "projected_qty": 0}
    if warehouse:
        bin_data = frappe.db.get_value(
            "Bin",
            {"item_code": item_code, "warehouse": warehouse},
            ["actual_qty", "reserved_qty", "projected_qty"],
            as_dict=True,
        )
        if bin_data:
            current_stock = {
                "actual_qty": flt(bin_data.actual_qty),
                "reserved_qty": flt(bin_data.reserved_qty),
                "projected_qty": flt(bin_data.projected_qty),
            }

    warehouse_stock = frappe.db.sql(
        """
        SELECT b.warehouse, b.actual_qty, b.reserved_qty, b.projected_qty, b.stock_value,
               w.warehouse_name
        FROM `tabBin` b
        LEFT JOIN `tabWarehouse` w ON w.name = b.warehouse
        WHERE b.item_code = %s AND w.company = %s AND b.actual_qty != 0
        ORDER BY b.warehouse
        """,
        (item_code, company),
        as_dict=True,
    )

    total_actual_qty = sum(flt(s.actual_qty) for s in warehouse_stock)

    return {
        "current_stock": current_stock,
        "warehouse_stock": warehouse_stock,
        "total_actual_qty": total_actual_qty,
    }


@frappe.whitelist()
def get_item_stock_all(item_code):
    """Get stock for an item across ALL companies.

    Returns:
        company_stock: list of {company, warehouse, actual_qty, stock_value}
        total_actual_qty: sum across all companies
    """
    if not item_code:
        return {"company_stock": [], "total_actual_qty": 0}

    warehouse_stock = frappe.db.sql(
        """
        SELECT b.warehouse, b.actual_qty, b.reserved_qty, b.projected_qty, b.stock_value,
               w.warehouse_name, w.company
        FROM `tabBin` b
        LEFT JOIN `tabWarehouse` w ON w.name = b.warehouse
        WHERE b.item_code = %s AND b.actual_qty != 0
        ORDER BY w.company, b.warehouse
        """,
        (item_code,),
        as_dict=True,
    )

    total_actual_qty = sum(flt(s.actual_qty) for s in warehouse_stock)

    return {
        "company_stock": warehouse_stock,
        "total_actual_qty": total_actual_qty,
    }


@frappe.whitelist()
def get_uom_details(item_code, uom):
    """Get conversion factor for an item's UOM."""
    from erpnext.stock.get_item_details import get_conversion_factor

    result = get_conversion_factor(item_code, uom)
    return result


@frappe.whitelist()
def get_item_uom(item_code):
    """Get Nos and Litre/Kg conversion factors for an item.

    Returns:
        nos_factor: pieces per Box (from UOM Conversion Detail Nos row)
        litre_factor: Litre/Kg per piece (from UOM Conversion Detail Litre/Kg row)

    LTR is fetched directly from the item conversion table.
    Total Litre = pcs x litre_factor.
    """
    uoms = frappe.get_all(
        "UOM Conversion Detail",
        filters={"parent": item_code, "uom": ["in", ["Nos", "Litre", "Kg"]]},
        fields=["uom", "conversion_factor"],
    )
    nos_factor = 1
    litre_factor = 0
    for u in uoms:
        if u.uom == "Nos":
            nos_factor = u.conversion_factor or 1
        elif u.uom in ("Litre", "Kg"):
            litre_factor = u.conversion_factor or 0

    item = frappe.get_doc("Item", item_code)
    return {
        "nos_factor": nos_factor,
        "litre_factor": litre_factor,
        "stock_uom": item.stock_uom,
    }


@frappe.whitelist()
def get_last_purchase_rate(item_code, supplier=None):
    """Get the last purchase rate for an item, optionally filtered by supplier."""
    filters = {
        "item_code": item_code,
        "docstatus": 1,
    }
    if supplier:
        filters["supplier"] = supplier

    last_po = frappe.db.get_value(
        "Purchase Invoice Item",
        filters,
        ["rate", "parent"],
        order_by="creation desc",
        as_dict=True,
    )

    if last_po:
        pi_date = frappe.db.get_value("Purchase Invoice", last_po.parent, "posting_date")
        return {"rate": last_po.rate, "date": pi_date, "pi_name": last_po.parent}

    # Fallback to Purchase Order
    last_po = frappe.db.get_value(
        "Purchase Order Item",
        filters,
        ["rate", "parent"],
        order_by="creation desc",
        as_dict=True,
    )
    if last_po:
        po_date = frappe.db.get_value("Purchase Order", last_po.parent, "transaction_date")
        return {"rate": last_po.rate, "date": po_date, "po_name": last_po.parent}

    return {"rate": 0, "date": None}


def _get_item_gst_rate(item_code, company):
    """Get GST rate for an item from Item Tax Template."""
    if not company:
        return 0

    # Try Item Tax Template
    item_tax = frappe.db.get_value(
        "Item Tax Template Detail",
        {"parenttype": "Item Tax Template", "tax_type": ["like", "%CGST%"]},
        ["parent", "tax_rate"],
        as_dict=True,
    )
    if item_tax:
        return item_tax.tax_rate

    # Try Company default
    company_doc = frappe.get_cached_doc("Company", company)
    if hasattr(company_doc, "default_gst_rate"):
        return company_doc.default_gst_rate

    return 0


def _get_default_warehouse(item_code, company):
    """Get default warehouse from Item defaults or Company."""
    if company:
        wh = frappe.db.get_value(
            "Item Default",
            {"parent": item_code, "company": company},
            "default_warehouse",
        )
        if wh:
            return wh

    if company:
        wh = frappe.get_cached_value("Company", company, "default_warehouse")
        if wh:
            return wh

    return None


def _get_expense_account(item_code, company):
    """Get expense account for purchase."""
    if company:
        acc = frappe.db.get_value(
            "Item Default",
            {"parent": item_code, "company": company},
            "expense_account",
        )
        if acc:
            return acc

        acc = frappe.get_cached_value("Company", company, "default_expense_account")
        if acc:
            return acc

    return None


def _get_income_account(item_code, company):
    """Get income account for sales."""
    if company:
        acc = frappe.db.get_value(
            "Item Default",
            {"parent": item_code, "company": company},
            "income_account",
        )
        if acc:
            return acc

        acc = frappe.get_cached_value("Company", company, "default_income_account")
        if acc:
            return acc

    return None


def _get_item_rate(item_code, company):
    """Get selling/buying rate from Price List."""
    price_list = frappe.db.get_value(
        "Buying Settings", None, "buying_price_list"
    ) or frappe.db.get_value(
        "Price List", {"buying": 1, "enabled": 1}, "name"
    )

    if not price_list:
        return 0

    rate = frappe.db.get_value(
        "Item Price",
        {"item_code": item_code, "price_list": price_list},
        "price_list_rate",
    )

    return rate or 0
