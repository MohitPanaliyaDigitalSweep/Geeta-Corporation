import frappe
from frappe.utils import flt

from fast_entry_app.api.item import get_pack_factors_bulk


def attach_stock_units(rows, factors):
    """Add qty_nos / qty_box / qty_ltr to each row, in place.

    qty_nos  pieces held (== actual_qty, the item's stock UOM)
    qty_box  full boxes held = pieces / pieces-per-box (0 if the item has no
             Box conversion, because "boxes" is then not a real unit for it)
    qty_ltr  litres held = pieces * litres-per-piece (0 when the item has no
             Litre/Kg conversion row)

    Both derived units are floors-of-reality, not guesses: a 3-pcs balance on a
    20-pcs/box pack is 0.15 box, so we keep full precision rather than rounding.
    """
    for r in rows:
        f = factors.get(r.item_code) or {}
        pieces = flt(r.actual_qty)
        nos_factor = flt(f.get("nos_factor")) or 1
        r.qty_nos = pieces
        r.qty_box = (pieces / nos_factor) if f.get("has_box") else 0
        r.qty_ltr = pieces * flt(f.get("litre_factor"))
        # Carried through so the UI can explain the derivation instead of
        # presenting converted numbers as if they were stored.
        r.box_factor = nos_factor if f.get("has_box") else 0
        r.litre_per_piece = flt(f.get("litre_factor"))


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

    # Per-warehouse breakdown (fetched before the pack factors so both result
    # sets can share a single factor lookup).
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
        SELECT item_code, warehouse, company, actual_qty, stock_value
        FROM `tabBin`
        WHERE {" AND ".join(bd_conditions)}
        ORDER BY company ASC, warehouse ASC
        """,
        bd_args,
        as_dict=True,
    )

    # On-hand balance expressed in the three units the business thinks in:
    # pieces (Nos, the stock UOM), boxes and litres. Derived live from
    # Bin.actual_qty + the Item's pack factors -- never persisted, so it can
    # never drift from actual_qty.
    #
    # NOTE: this replaces the previous total_box/total_pcs/total_ltr columns,
    # which were all-time sums of fe_* over every submitted invoice (i.e. stock
    # FLOW, not the balance). Sitting next to an on-hand stock_value they were
    # actively misleading, and stock_value / total_pcs mixed the two.
    factors = get_pack_factors_bulk(
        sorted({r.item_code for r in rows} | {r.item_code for r in bd_rows})
    )
    attach_stock_units(rows, factors)
    attach_stock_units(bd_rows, factors)

    breakdown = {}
    for r in bd_rows:
        breakdown.setdefault(r.item_code, []).append(r)

    # Which companies actually hold this item's stock. Used by the "All
    # Companies" view to badge each row with the owning company.
    item_companies = {}
    for r in bd_rows:
        item_companies.setdefault(r.item_code, [])
        if r.company not in item_companies[r.item_code]:
            item_companies[r.item_code].append(r.company)

    for r in rows:
        r.companies = item_companies.get(r.item_code, [])

    return {
        "rows": rows,
        "breakdown": breakdown,
        "all_companies": all_companies,
        "companies": frappe.get_all("Company", fields=["name", "abbr"], order_by="name asc"),
    }


@frappe.whitelist()
def get_item_transactions(item_code, warehouse=None, from_date=None, to_date=None, company=None):
    if not item_code:
        return []

    conditions = ["item_code = %s", "is_cancelled = 0"]
    args = [item_code]

    # Respect the company filter. Without this the drill-down silently shows
    # every company's movements for the item even when one company is selected.
    if company and company != "__all__":
        if "," in company:
            company_list = [c.strip() for c in company.split(",") if c.strip()]
            if company_list:
                placeholders = ", ".join(["%s"] * len(company_list))
                conditions.append(f"company IN ({placeholders})")
                args.extend(company_list)
        else:
            conditions.append("company = %s")
            args.append(company)

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
            company,
            warehouse,
            voucher_type,
            voucher_no,
            actual_qty,
            qty_after_transaction,
            valuation_rate,
            stock_value_difference
        FROM `tabStock Ledger Entry`
        WHERE {where}
        ORDER BY company ASC, posting_datetime ASC, name ASC
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
    all_companies = not company or company == "__all__"
    if company and company != "__all__":
        if "," in company:
            company_list = [c.strip() for c in company.split(",") if c.strip()]
            filters["company"] = ["in", company_list]
        else:
            filters["company"] = company

    rows = frappe.get_all(
        "Warehouse",
        filters=filters,
        fields=["name", "warehouse_name", "company"],
        order_by="company asc, name asc",
    )

    # In the "All Companies" view two companies can both own a "Stores"
    # warehouse, so the label carries the company abbreviation too.
    for r in rows:
        short = (r.warehouse_name or r.name).split(" - ")[0]
        r.short_name = short
        r.label = f"{short} ({r.company})" if all_companies else (r.warehouse_name or r.name)

    return rows


# ── Standard "Stock Balance" report augmentation ───────────────────────────────
#
# The built-in ERPNext query report `Stock Balance` is a Script Report whose
# front end calls `frappe.desk.query_report.run`. We intercept that whitelisted
# method (see hooks.override_whitelisted_methods), let the original run
# untouched, then splice in the same Box / Pcs / LTR pack-UOM columns the Fast
# Entry stock report shows. Values reuse the exact derivations from
# item.get_pack_factors_bulk (via attach_stock_units), so both reports agree:
#
#   qty_pcs  = balance qty (stock UOM is Nos after the Option B migration)
#   qty_box  = pieces / pieces-per-box   (0 when the item has no Box conversion)
#   qty_ltr  = pieces * litres-per-piece (0 when there is no Litre/Kg row)
#
# The total row is skipped deliberately: adding boxes/litres across packs of
# different sizes is meaningless, and the total is pinned to the original
# columns because add_total_row runs inside the original call.

REPORT_NAME_STOCK_BALANCE = "Stock Balance"

_PACK_COLUMNS = (
    ("Box", "qty_box"),
    ("Pcs", "qty_pcs"),
    ("Ltr", "qty_ltr"),
)


@frappe.whitelist()
def override_query_report_run(*args, **kwargs):
    """Wrap frappe.desk.query_report.run: original result + Stock Balance pack UOM."""
    report_name = kwargs.get("report_name") or (args[0] if args else None)

    result = frappe.get_attr("frappe.desk.query_report.run")(*args, **kwargs)

    if report_name == REPORT_NAME_STOCK_BALANCE:
        try:
            _augment_stock_balance(result)
        except Exception:
            # Never break the standard report; log and fall back to stock output.
            frappe.log_error(frappe.get_traceback(), "fast_entry_app: augment Stock Balance")
    return result


def _augment_stock_balance(result):
    columns = result.get("columns") or []
    rows = result.get("result") or []

    bal_idx = None
    for i, col in enumerate(columns):
        if isinstance(col, dict) and col.get("fieldname") == "bal_qty":
            bal_idx = i
            break
    if bal_idx is None:
        return

    for insert_delta, (label, fieldname) in enumerate(_PACK_COLUMNS, start=1):
        columns.insert(
            bal_idx + insert_delta,
            {
                "label": label,
                "fieldname": fieldname,
                "fieldtype": "Float",
                "width": 90,
            },
        )

    item_codes = [r.get("item_code") for r in rows if isinstance(r, dict) and r.get("item_code")]
    factors = get_pack_factors_bulk(item_codes) if item_codes else {}

    for r in rows:
        # Skip the total row: it is appended by add_total_row as a plain list
        # (never normalized to a dict), and summing boxes/litres across packs of
        # different sizes would be meaningless anyway. Consolidated/grouped
        # rows (no item_code) also have nothing to derive from.
        if not isinstance(r, dict):
            continue

        code = r.get("item_code")
        if not code or r.get("is_total_row"):
            r["qty_box"] = r["qty_pcs"] = r["qty_ltr"] = None
            continue

        f = factors.get(code) or {}
        pieces = flt(r.get("bal_qty"))
        pcs_per_box = flt(f.get("nos_factor")) or 1

        r["qty_pcs"] = pieces
        r["qty_box"] = (pieces / pcs_per_box) if f.get("has_box") else 0.0
        r["qty_ltr"] = pieces * flt(f.get("litre_factor"))
