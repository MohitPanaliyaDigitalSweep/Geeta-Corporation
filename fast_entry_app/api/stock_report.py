import frappe
from frappe.utils import flt

ITEM_DOCTYPES = [
    ("Delivery Note Item", "Delivery Note"),
    ("Purchase Receipt Item", "Purchase Receipt"),
    ("Sales Invoice Item", "Sales Invoice"),
    ("Purchase Invoice Item", "Purchase Invoice"),
]


def _build_fe_union_flat(company_filter=None):
    queries = []
    args = []
    for item_dt, parent_dt in ITEM_DOCTYPES:
        conditions = ["p.docstatus = 1"]
        if company_filter == "__all__":
            pass
        elif company_filter and "," in company_filter:
            placeholders = ", ".join(["%s"] * len(company_filter))
            conditions.append(f"p.company IN ({placeholders})")
            args.extend([c.strip() for c in company_filter.split(",") if c.strip()])
        elif company_filter:
            conditions.append("p.company = %s")
            args.append(company_filter)

        queries.append(f"""
            SELECT t.item_code,
                   SUM(t.fe_box) AS total_box,
                   SUM(t.fe_pcs) AS total_pcs,
                   SUM(t.fe_total_ltr) AS total_ltr
            FROM `tab{item_dt}` t
            JOIN `tab{parent_dt}` p ON p.name = t.parent
            WHERE {' AND '.join(conditions)}
            GROUP BY t.item_code
        """)
    return " UNION ALL ".join(queries), args


def _build_fe_union(company_filter=None):
    queries = []
    args = []
    for item_dt, parent_dt in ITEM_DOCTYPES:
        conditions = ["p.docstatus = 1"]
        if company_filter == "__all__":
            pass
        elif company_filter and "," in company_filter:
            placeholders = ", ".join(["%s"] * len(company_filter))
            conditions.append(f"p.company IN ({placeholders})")
            args.extend([c.strip() for c in company_filter.split(",") if c.strip()])
        elif company_filter:
            conditions.append("p.company = %s")
            args.append(company_filter)

        queries.append(f"""
            SELECT t.item_code, t.warehouse,
                   SUM(t.fe_box) AS total_box,
                   SUM(t.fe_pcs) AS total_pcs,
                   SUM(t.fe_total_ltr) AS total_ltr
            FROM `tab{item_dt}` t
            JOIN `tab{parent_dt}` p ON p.name = t.parent
            WHERE {' AND '.join(conditions)}
            GROUP BY t.item_code, t.warehouse
        """)
    return " UNION ALL ".join(queries), args


@frappe.whitelist()
def get_stock_summary(company, warehouse=None, search=None):
    if not company:
        return {"rows": [], "breakdown": {}}

    all_companies = (company == "__all__")
    multi_company = not all_companies and "," in company
    company_list = [c.strip() for c in company.split(",") if c.strip()] if multi_company else None

    conditions = []
    args = []

    if not all_companies:
        if multi_company:
            placeholders = ", ".join(["%s"] * len(company_list))
            conditions.append(f"b.company IN ({placeholders})")
            args.extend(company_list)
        else:
            conditions.append("b.company = %s")
            args.append(company)

    if warehouse:
        conditions.append("b.warehouse = %s")
        args.append(warehouse)

    if search:
        conditions.append("(b.item_code LIKE %s OR i.item_name LIKE %s)")
        args += [f"%{search}%", f"%{search}%"]
    else:
        conditions.append("(b.actual_qty != 0 OR b.reserved_qty != 0 OR b.projected_qty != 0)")

    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            b.item_code,
            i.item_name,
            i.stock_uom,
            SUM(b.actual_qty) AS actual_qty,
            SUM(b.stock_value) AS stock_value
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        WHERE {where}
        GROUP BY b.item_code, i.item_name, i.stock_uom
        ORDER BY i.item_name ASC
        """,
        args,
        as_dict=True,
    )

    # Aggregate fe_box / fe_pcs / fe_total_ltr from ALL 6 item doctypes
    flat_sql, fe_args = _build_fe_union_flat(company)
    fe_data = frappe.db.sql(flat_sql, fe_args, as_dict=True)
    fe_map = {}
    for r in fe_data:
        fe_map.setdefault(r.item_code, {"box": 0, "pcs": 0, "ltr": 0})
        fe_map[r.item_code]["box"] += flt(r.total_box)
        fe_map[r.item_code]["pcs"] += flt(r.total_pcs)
        fe_map[r.item_code]["ltr"] += flt(r.total_ltr)

    for r in rows:
        fe = fe_map.get(r.item_code, {})
        r.total_box = fe.get("box", 0)
        r.total_pcs = fe.get("pcs", 0)
        r.total_ltr = fe.get("ltr", 0)

    # Per-warehouse breakdown
    bd_conditions = ["actual_qty != 0"]
    bd_args = []
    if not all_companies:
        if multi_company:
            placeholders = ", ".join(["%s"] * len(company_list))
            bd_conditions.append(f"company IN ({placeholders})")
            bd_args.extend(company_list)
        else:
            bd_conditions.append("company = %s")
            bd_args.append(company)

    bd_rows = frappe.db.sql(
        f"""
        SELECT item_code, warehouse, actual_qty, stock_value
        FROM `tabBin`
        WHERE {" AND ".join(bd_conditions)}
        ORDER BY warehouse ASC
        """,
        bd_args,
        as_dict=True,
    )

    # Get warehouse-level fe_* from all 6 item doctypes
    breakdown = {}
    wh_sql, wh_fe_args = _build_fe_union(company)
    wh_fe_data = frappe.db.sql(wh_sql, wh_fe_args, as_dict=True)
    wh_fe_map = {}
    for r in wh_fe_data:
        key = (r.item_code, r.warehouse)
        entry = wh_fe_map.setdefault(key, {"box": 0, "pcs": 0, "ltr": 0})
        entry["box"] += flt(r.total_box)
        entry["pcs"] += flt(r.total_pcs)
        entry["ltr"] += flt(r.total_ltr)

    for r in bd_rows:
        key = (r.item_code, r.warehouse)
        fe = wh_fe_map.get(key, {})
        r.total_box = fe.get("box", 0)
        r.total_pcs = fe.get("pcs", 0)
        r.total_ltr = fe.get("ltr", 0)
        breakdown.setdefault(r.item_code, []).append(r)

    return {"rows": rows, "breakdown": breakdown}


@frappe.whitelist()
def get_item_transactions(item_code, warehouse=None, from_date=None, to_date=None):
    if not item_code:
        return []

    conditions = ["item_code = %s", "is_cancelled = 0"]
    args = [item_code]

    if warehouse:
        conditions.append("warehouse = %s")
        args.append(warehouse)

    if from_date:
        conditions.append("posting_date >= %s")
        args.append(from_date)

    if to_date:
        conditions.append("posting_date <= %s")
        args.append(to_date)

    where = " AND ".join(conditions)

    rows = frappe.db.sql(
        f"""
        SELECT
            posting_date,
            posting_time,
            warehouse,
            voucher_type,
            voucher_no,
            actual_qty,
            qty_after_transaction,
            valuation_rate,
            stock_value_difference
        FROM `tabStock Ledger Entry`
        WHERE {where}
        ORDER BY posting_datetime ASC, name ASC
        """,
        args,
        as_dict=True,
    )

    # Enrich all relevant voucher types with fe_*
    voucher_type_map = {
        "Purchase Invoice": "Purchase Invoice Item",
        "Sales Invoice": "Sales Invoice Item",
        "Delivery Note": "Delivery Note Item",
        "Purchase Receipt": "Purchase Receipt Item",
    }

    for vtype, item_dt in voucher_type_map.items():
        vouchers = [
            r.voucher_no for r in rows if r.voucher_type == vtype
        ]
        if not vouchers:
            continue
        voucher_names = list(set(vouchers))
        placeholders = ", ".join(["%s"] * len(voucher_names))
        items = frappe.db.sql(
            f"""
            SELECT parent,
                   SUM(fe_box) AS total_box,
                   SUM(fe_pcs) AS total_pcs,
                   SUM(fe_total_ltr) AS total_ltr
            FROM `tab{item_dt}`
            WHERE parent IN ({placeholders})
            GROUP BY parent
            """,
            voucher_names,
            as_dict=True,
        )
        p_map = {r.parent: r for r in items}
        for r in rows:
            if r.voucher_type == vtype and r.voucher_no in p_map:
                pi = p_map[r.voucher_no]
                r.total_box = pi.total_box
                r.total_pcs = pi.total_pcs
                r.total_ltr = pi.total_ltr

    return rows


@frappe.whitelist()
def get_warehouses(company=None):
    filters = {"is_group": 0, "disabled": 0}
    if company and company != "__all__":
        if "," in company:
            company_list = [c.strip() for c in company.split(",") if c.strip()]
            filters["company"] = ["in", company_list]
        else:
            filters["company"] = company
    return frappe.get_all(
        "Warehouse",
        filters=filters,
        fields=["name", "warehouse_name", "company"],
        order_by="name asc",
    )
