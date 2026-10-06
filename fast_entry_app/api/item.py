import frappe
from frappe import _
from frappe.utils import flt

# The UOM Fast Entry books every transaction in. It is a single named constant
# because it is a semantic property of the app (entries are counted in pieces),
# not a per-document value -- the concrete UOM written on a row is always read
# from the Item master via get_invoice_uom().
PIECE_UOM = "Nos"


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
def _pack_factors_from_uom_map(uom_map, stock_uom):
    """Pure pack-factor derivation shared by the single and bulk readers.

    Handles both conversion-table layouts so it works before and after the
    Option B migration (maintenance/stock_uom_to_pieces.py):

    Option B (piece-based, Nos anchor)   Legacy (box-based)
      stock_uom = Nos                      stock_uom = Box
      Nos  cf = 1                          Box  cf = 1
      Box  cf = P  <- pieces per box       Nos  cf = P  <- pieces per box

    In both layouts P is the factor of whichever of {Box, Nos} is NOT the stock
    UOM, so derive it from the pair rather than hardcoding one row.

    litre_factor is always read straight from the Litre (or Kg) row, which holds
    "litres per piece". That row is intentionally left untouched by the migration
    (see that module's docstring), so this is layout-independent.
    """
    nos_cf = uom_map.get("Nos", 0)
    box_cf = uom_map.get("Box", 0)

    non_stock_cf = box_cf if stock_uom == "Nos" else nos_cf
    pcs_per_box = non_stock_cf if non_stock_cf >= 1 else 1

    litre_per_piece = uom_map.get("Litre", 0) or uom_map.get("Kg", 0)
    if litre_per_piece < 0:
        litre_per_piece = 0

    return {
        "nos_factor": pcs_per_box,
        "litre_factor": litre_per_piece,
        "has_box": 1 if uom_map.get("Box") else 0,
    }


@frappe.whitelist()
def get_item_uom(item_code):
    """Get pieces-per-box (nos_factor) and litres-per-piece (litre_factor)."""
    item = frappe.get_cached_doc("Item", item_code)
    uom_map = {u.uom: flt(u.conversion_factor or 0) for u in (item.uoms or [])}
    stock_uom = item.stock_uom

    factors = _pack_factors_from_uom_map(uom_map, stock_uom)

    return {
        "nos_factor": factors["nos_factor"],
        "litre_factor": factors["litre_factor"],
        "stock_uom": stock_uom,
        # Read, never assumed: the UOM + factor a transaction row must be booked in.
        # The client writes these instead of hardcoding "Nos"/1.0, which silently
        # inflated stock by the pack size on any un-migrated (Box-stock) item.
        "has_box": factors["has_box"],
        "invoice_uom": stock_uom,
        "conversion_factor": flt(uom_map.get(stock_uom, 1) or 1),
    }


def get_pack_factors_bulk(item_codes):
    """Pack factors for many items in one round trip.

    Returns {item_code: {"nos_factor", "litre_factor", "has_box"}}. Same
    derivation as get_item_uom(); it exists so report-style callers that need a
    whole item list do not pay one cached-doc read per row.
    """
    item_codes = [c for c in (item_codes or []) if c]
    if not item_codes:
        return {}

    rows = frappe.db.sql(
        """
        SELECT parent AS item_code, uom, conversion_factor
        FROM `tabUOM Conversion Detail`
        WHERE parenttype = 'Item' AND parent IN %(items)s
        """,
        {"items": item_codes},
        as_dict=True,
    )

    maps = {}
    for r in rows:
        maps.setdefault(r.item_code, {})[r.uom] = flt(r.conversion_factor or 0)

    stock_uoms = {
        d.name: d.stock_uom
        for d in frappe.get_all("Item", filters={"name": ["in", item_codes]}, fields=["name", "stock_uom"])
    }

    out = {}
    for code in item_codes:
        uom_map = maps.get(code, {})
        out[code] = _pack_factors_from_uom_map(uom_map, stock_uoms.get(code) or "Nos")
    return out


def get_invoice_uom(item_code):
    """Return the UOM a transaction row must be booked in, derived from the Item.

    Fast Entry always books transactions in individual pieces and relies on
    ERPNext's own invariant that a stock UOM always has conversion_factor 1
    (see erpnext.controllers.transaction_base.validate_conversion_factor).
    That invariant is why stock_qty == qty for these rows.

    So the correct UOM is simply the item's own stock_uom -- it is read from the
    master rather than hardcoded, and the factor is derived from that same row.

    A stock UOM other than "Nos" means the master is still piece-in-a-box (i.e.
    the Option B migration has not been run). Booking pieces in that UOM would
    understate stock by the pack size, so fail loudly and point at the migration
    rather than silently corrupting quantities.
    """
    item = frappe.get_cached_doc("Item", item_code)
    stock_uom = item.stock_uom

    if not stock_uom:
        frappe.throw(
            _("Item {0} has no Stock UOM set.").format(item_code),
            title=_("Cannot Create Entry"),
        )

    if stock_uom != PIECE_UOM:
        frappe.throw(
            _(
                "Item {0} is stocked in {1}, but Fast Entry books entries in {2} "
                "per piece. Running it in {1} would record {2} pieces as {1} units. "
                "Run the Option B migration for this site first: "
                "bench --site {3} execute "
                "fast_entry_app.maintenance.stock_uom_to_pieces.execute --kwargs "
                "'{{\"dry_run\": false}}'"
            ).format(item_code, stock_uom, PIECE_UOM, frappe.local.site),
            title=_("Stock UOM Not Migrated"),
        )

    uom_row = next((u for u in (item.uoms or []) if u.uom == stock_uom), None)
    conversion_factor = flt(uom_row.conversion_factor) if uom_row else 1.0
    if not conversion_factor:
        # The anchor row is missing; ERPNext would reject this at validate time
        # anyway, so surface the real cause here instead.
        conversion_factor = 1.0

    return {"uom": stock_uom, "conversion_factor": conversion_factor}


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
    """GST rate applicable to an item, used by the entry screens' tax preview.

    Order: Item Tax Template row, then the company's own default rate. Falls
    back to 0 only when neither exists.

    The company fallback matters: sales/purchase/quotation all charge the
    company's default taxes-and-charges template when no tax override is
    selected, so without it the screens showed 0.00 CGST/SGST/IGST while the
    saved document carried real tax. (The previous fallback read
    `Company.default_gst_rate`, which is not a column in this build.)

    Preview-only: no API computes saved tax from this value.
    """
    if not company:
        return 0

    # Per-item tax template — scoped to THIS item. An unscoped lookup would
    # match an arbitrary row of any company's Item Tax Template (e.g. "GST 12%".
    # or "Exempted" from another firm) and return a wrong or zero rate. This
    # build has no Item.item_tax_template column, so the guard keeps it a
    # portable no-op here and falls through to the company default.
    if frappe.db.has_column("Item", "item_tax_template"):
        item_tax_template = frappe.db.get_value("Item", item_code, "item_tax_template")
        if item_tax_template:
            rate = frappe.db.get_value(
                "Item Tax Template Detail",
                {"parent": item_tax_template, "tax_type": ["like", "%CGST%"]},
                "tax_rate",
            )
            if rate is not None:
                # CGST rows carry half the intra-state rate; the preview shows
                # the total (CGST+SGST), so double it.
                return flt(rate) * 2

    # Company default: total GST rate of the company's default tax template.
    # This is direction-independent (CGST+SGST and IGST are the same rate), so
    # it is correct for both intra- and inter-state previews; the client
    # decides how to split it based on the selected GST type.
    # Lazy import: api.sales imports this module, so a module-level import
    # here would be circular.
    try:
        from fast_entry_app.api.sales import _company_tax_rate
        return flt(_company_tax_rate(company))
    except Exception:
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
