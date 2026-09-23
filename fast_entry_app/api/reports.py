import json
import frappe
from frappe import _
from frappe.utils import flt, getdate, add_months, add_days, date_diff, today


# ═══════════════════════════════════════════════════════════════
# SHARED FILTER OPTIONS
# ═══════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_filter_options():
    sales_persons = frappe.get_all("Sales Person", filters={"enabled": 1}, pluck="name")
    companies = frappe.get_all("Company", pluck="name")
    customers = frappe.db.sql(
        "SELECT DISTINCT si.customer FROM `tabSales Invoice` si "
        "WHERE si.docstatus = 1 AND si.customer IS NOT NULL ORDER BY si.customer",
        pluck=True,
    )
    suppliers = frappe.db.sql(
        "SELECT DISTINCT pi.supplier FROM `tabPurchase Invoice` pi "
        "WHERE pi.docstatus = 1 AND pi.supplier IS NOT NULL ORDER BY pi.supplier",
        pluck=True,
    )
    party_groups = frappe.db.sql(
        "SELECT DISTINCT pg.name FROM `tabParty Group` pg "
        "ORDER BY pg.name",
        pluck=True,
    )
    items = frappe.db.sql(
        "SELECT DISTINCT sii.item_name FROM `tabSales Invoice Item` sii "
        "INNER JOIN `tabSales Invoice` si ON si.name = sii.parent "
        "WHERE si.docstatus = 1 AND sii.item_name IS NOT NULL AND sii.item_name != '' "
        "ORDER BY sii.item_name",
        pluck=True,
    )
    pincodes = frappe.db.sql(
        "SELECT DISTINCT addr.pincode FROM `tabAddress` addr "
        "WHERE addr.pincode IS NOT NULL AND addr.pincode != '' ORDER BY addr.pincode",
        pluck=True,
    )

    return {
        "sales_persons": sales_persons,
        "companies": companies,
        "customers": customers,
        "suppliers": suppliers,
        "party_groups": party_groups,
        "items": items,
        "pincodes": pincodes,
    }


# ═══════════════════════════════════════════════════════════════
# PERIOD HELPER
# ═══════════════════════════════════════════════════════════════

def _get_previous_period(from_date, to_date, period):
    fd = getdate(from_date)
    td = getdate(to_date)
    days = date_diff(td, fd) + 1
    if period == "month":
        prev_fd = add_months(fd, -1)
        prev_td = add_days(prev_fd, days - 1)
    elif period == "quarter":
        prev_fd = add_months(fd, -3)
        prev_td = add_days(prev_fd, days - 1)
    elif period == "year":
        prev_fd = add_months(fd, -12)
        prev_td = add_days(prev_fd, days - 1)
    else:
        prev_td = add_days(fd, -1)
        prev_fd = add_days(prev_td, -(days - 1))
    return str(prev_fd), str(prev_td)


def _add_diff_fields(s):
    for field in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "grand_total", "outstanding_amount"]:
        if field not in s:
            continue
        cur = s.get(f"cur_{field}", 0)
        prev = s.get(f"prev_{field}", 0)
        diff = cur - prev
        pct = (diff / prev * 100) if prev else (100 if cur else 0)
        s[f"diff_{field}"] = diff
        s[f"pct_{field}"] = round(pct, 1)


def _fmt(v):
    return (v or 0).toLocaleString("en-IN", {"minimumFractionDigits": 2, "maximumFractionDigits": 2})


# ═══════════════════════════════════════════════════════════════
# REPORT 1: SALES PERSON DETAILED
# ═══════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_sp_detail_report(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    period = filters.get("period", "custom")
    sales_persons = filters.get("sales_persons", [])
    companies = filters.get("companies", [])
    items = filters.get("items", [])
    pincodes = filters.get("pincodes", [])
    customers = filters.get("customers", [])

    if not from_date or not to_date:
        frappe.throw(_("From Date and To Date are required"))

    prev_from, prev_to = _get_previous_period(from_date, to_date, period)

    current_data = _sp_detail_query(from_date, to_date, sales_persons, companies, items, pincodes, customers)
    prev_data = _sp_detail_query(prev_from, prev_to, sales_persons, companies, items, pincodes, customers)

    merged = _sp_detail_merge(current_data, prev_data)

    return {
        "current_period": {"from_date": from_date, "to_date": to_date},
        "previous_period": {"from_date": prev_from, "to_date": prev_to},
        "data": merged,
        "summary": _sp_detail_summary(merged),
        "charts": _sp_detail_charts(merged),
    }


def _sp_detail_query(fd, td, sales_persons=None, companies=None, items=None, pincodes=None, customers=None):
    conditions = ["si.docstatus = 1", "si.fe_sales_person IS NOT NULL", "si.fe_sales_person != ''"]
    params = [fd, td]
    conditions.append("si.posting_date BETWEEN %s AND %s")

    if sales_persons:
        placeholders = ",".join(["%s"] * len(sales_persons))
        conditions.append(f"si.fe_sales_person IN ({placeholders})")
        params.extend(sales_persons)
    if companies:
        placeholders = ",".join(["%s"] * len(companies))
        conditions.append(f"si.company IN ({placeholders})")
        params.extend(companies)
    if items:
        placeholders = ",".join(["%s"] * len(items))
        conditions.append(f"sii.item_name IN ({placeholders})")
        params.extend(items)
    if pincodes:
        placeholders = ",".join(["%s"] * len(pincodes))
        conditions.append(f"addr.pincode IN ({placeholders})")
        params.extend(pincodes)
    if customers:
        placeholders = ",".join(["%s"] * len(customers))
        conditions.append(f"si.customer IN ({placeholders})")
        params.extend(customers)

    where_clause = " AND ".join(conditions)
    return frappe.db.sql(f"""
        SELECT
            si.fe_sales_person AS sales_person,
            si.customer,
            COALESCE(addr.pincode, '') AS pincode,
            sii.item_name,
            si.posting_date,
            si.company,
            si.name AS invoice_no,
            COALESCE(sii.fe_box, 0) AS box,
            COALESCE(sii.fe_pcs, 0) AS pcs,
            COALESCE(sii.fe_ltr, 0) AS ltr,
            COALESCE(sii.fe_total_ltr, 0) AS total_ltr,
            sii.qty,
            sii.rate,
            sii.amount,
            si.grand_total
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE {where_clause}
        ORDER BY si.fe_sales_person, si.customer, sii.item_name
    """, params, as_dict=True)


def _sp_detail_merge(current, previous):
    result = {}
    for row in current:
        key = (row.sales_person, row.customer, row.item_name)
        if key not in result:
            result[key] = {
                "sales_person": row.sales_person, "customer": row.customer,
                "item_name": row.item_name,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0,
            }
        r = result[key]
        r["cur_box"] += flt(row.box)
        r["cur_pcs"] += flt(row.pcs)
        r["cur_ltr"] += flt(row.ltr)
        r["cur_total_ltr"] += flt(row.total_ltr)
        r["cur_qty"] += flt(row.qty)
        r["cur_amount"] += flt(row.amount)
        r["cur_invoices"] += 1

    for row in previous:
        key = (row.sales_person, row.customer, row.item_name)
        if key not in result:
            result[key] = {
                "sales_person": row.sales_person, "customer": row.customer,
                "item_name": row.item_name,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0,
            }
        r = result[key]
        r["prev_box"] += flt(row.box)
        r["prev_pcs"] += flt(row.pcs)
        r["prev_ltr"] += flt(row.ltr)
        r["prev_total_ltr"] += flt(row.total_ltr)
        r["prev_qty"] += flt(row.qty)
        r["prev_amount"] += flt(row.amount)
        r["prev_invoices"] += 1

    for r in result.values():
        _add_diff_fields(r)
    return sorted(result.values(), key=lambda x: (-x["cur_amount"], x["sales_person"]))


def _sp_detail_summary(data):
    sp = {}
    for r in data:
        s = r["sales_person"]
        if s not in sp:
            sp[s] = {
                "sales_person": s, "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0,
                "cur_total_ltr": 0, "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0,
                "customers": set(), "items": set(),
            }
        for f in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "invoices"]:
            sp[s][f"cur_{f}"] += r[f"cur_{f}"]
            sp[s][f"prev_{f}"] += r[f"prev_{f}"]
        sp[s]["customers"].add(r["customer"])
        sp[s]["items"].add(r["item_name"])

    result = []
    for s, v in sorted(sp.items(), key=lambda x: -x[1]["cur_amount"]):
        v["customer_count"] = len(v["customers"])
        v["item_count"] = len(v["items"])
        del v["customers"]
        del v["items"]
        _add_diff_fields(v)
        result.append(v)
    return result


def _sp_detail_charts(data):
    sp_amount = {}
    sp_pcs = {}
    item_amount = {}
    for r in data:
        s = r["sales_person"]
        sp_amount[s] = sp_amount.get(s, 0) + r["cur_amount"]
        sp_pcs[s] = sp_pcs.get(s, 0) + r["cur_pcs"]
        i = r["item_name"]
        item_amount[i] = item_amount.get(i, 0) + r["cur_amount"]

    sp_labels = sorted(sp_amount, key=sp_amount.get, reverse=True)
    item_labels = sorted(item_amount, key=item_amount.get, reverse=True)[:10]
    return {
        "kpis": _build_kpis(data),
        "sp_amount": {"labels": sp_labels, "values": [round(sp_amount[k], 2) for k in sp_labels]},
        "sp_pcs": {"labels": sp_labels, "values": [round(sp_pcs[k], 2) for k in sp_labels]},
        "item_amount": {"labels": item_labels, "values": [round(item_amount[k], 2) for k in item_labels]},
    }


def _build_kpis(data, prefix=""):
    total_cur_amount = sum(r.get(f"cur_amount", 0) for r in data)
    total_prev_amount = sum(r.get("prev_amount", 0) for r in data)
    total_cur_invoices = sum(r.get("cur_invoices", 0) for r in data)
    total_prev_invoices = sum(r.get("prev_invoices", 0) for r in data)
    total_cur_pcs = sum(r.get("cur_pcs", 0) for r in data)
    total_prev_pcs = sum(r.get("prev_pcs", 0) for r in data)
    total_cur_box = sum(r.get("cur_box", 0) for r in data)
    total_prev_box = sum(r.get("prev_box", 0) for r in data)
    total_cur_ltr = sum(r.get("cur_ltr", 0) for r in data)
    total_prev_ltr = sum(r.get("prev_ltr", 0) for r in data)

    avg_order = total_cur_amount / total_cur_invoices if total_cur_invoices else 0
    prev_avg_order = total_prev_amount / total_prev_invoices if total_prev_invoices else 0

    return {
        "total_amount": {"cur": round(total_cur_amount, 2), "prev": round(total_prev_amount, 2)},
        "total_invoices": {"cur": total_cur_invoices, "prev": total_prev_invoices},
        "avg_order": {"cur": round(avg_order, 2), "prev": round(prev_avg_order, 2)},
        "total_pcs": {"cur": round(total_cur_pcs, 2), "prev": round(total_prev_pcs, 2)},
        "total_box": {"cur": round(total_cur_box, 2), "prev": round(total_prev_box, 2)},
        "total_ltr": {"cur": round(total_cur_ltr, 2), "prev": round(total_prev_ltr, 2)},
    }


# ═══════════════════════════════════════════════════════════════
# REPORT 2: AREA WISE PRODUCT POTENTIAL
# ═══════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_area_potential_report(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    period = filters.get("period", "custom")
    companies = filters.get("companies", [])
    items = filters.get("items", [])
    pincodes = filters.get("pincodes", [])

    if not from_date or not to_date:
        frappe.throw(_("From Date and To Date are required"))

    prev_from, prev_to = _get_previous_period(from_date, to_date, period)

    current_data = _area_query(from_date, to_date, companies, items, pincodes)
    prev_data = _area_query(prev_from, prev_to, companies, items, pincodes)

    merged = _area_merge(current_data, prev_data)

    return {
        "current_period": {"from_date": from_date, "to_date": to_date},
        "previous_period": {"from_date": prev_from, "to_date": prev_to},
        "data": merged,
        "pincode_summary": _area_pincode_summary(merged),
        "product_summary": _area_product_summary(merged),
        "charts": _area_charts(merged),
    }


def _area_query(fd, td, companies=None, items=None, pincodes=None):
    conditions = ["si.docstatus = 1"]
    params = [fd, td]
    conditions.append("si.posting_date BETWEEN %s AND %s")

    if companies:
        placeholders = ",".join(["%s"] * len(companies))
        conditions.append(f"si.company IN ({placeholders})")
        params.extend(companies)
    if items:
        placeholders = ",".join(["%s"] * len(items))
        conditions.append(f"sii.item_name IN ({placeholders})")
        params.extend(items)
    if pincodes:
        placeholders = ",".join(["%s"] * len(pincodes))
        conditions.append(f"addr.pincode IN ({placeholders})")
        params.extend(pincodes)

    where_clause = " AND ".join(conditions)
    return frappe.db.sql(f"""
        SELECT
            COALESCE(addr.pincode, 'No Pincode') AS pincode,
            COALESCE(addr.city, '') AS city,
            sii.item_name,
            si.customer,
            si.fe_sales_person AS sales_person,
            si.company,
            si.name AS invoice_no,
            si.posting_date,
            COALESCE(sii.fe_box, 0) AS box,
            COALESCE(sii.fe_pcs, 0) AS pcs,
            COALESCE(sii.fe_ltr, 0) AS ltr,
            COALESCE(sii.fe_total_ltr, 0) AS total_ltr,
            sii.qty,
            sii.rate,
            sii.amount,
            si.grand_total
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE {where_clause}
        ORDER BY addr.pincode, sii.item_name
    """, params, as_dict=True)


def _area_merge(current, previous):
    result = {}
    for row in current:
        key = (row.pincode, row.item_name)
        if key not in result:
            result[key] = {
                "pincode": row.pincode, "city": row.city, "item_name": row.item_name,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0, "cur_customers": set(),
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0, "prev_customers": set(),
            }
        r = result[key]
        r["cur_box"] += flt(row.box)
        r["cur_pcs"] += flt(row.pcs)
        r["cur_ltr"] += flt(row.ltr)
        r["cur_total_ltr"] += flt(row.total_ltr)
        r["cur_qty"] += flt(row.qty)
        r["cur_amount"] += flt(row.amount)
        r["cur_invoices"] += 1
        r["cur_customers"].add(row.customer)

    for row in previous:
        key = (row.pincode, row.item_name)
        if key not in result:
            result[key] = {
                "pincode": row.pincode, "city": row.city, "item_name": row.item_name,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0, "cur_customers": set(),
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0, "prev_customers": set(),
            }
        r = result[key]
        r["prev_box"] += flt(row.box)
        r["prev_pcs"] += flt(row.pcs)
        r["prev_ltr"] += flt(row.ltr)
        r["prev_total_ltr"] += flt(row.total_ltr)
        r["prev_qty"] += flt(row.qty)
        r["prev_amount"] += flt(row.amount)
        r["prev_invoices"] += 1
        r["prev_customers"].add(row.customer)

    for r in result.values():
        r["cur_customer_count"] = len(r["cur_customers"])
        r["prev_customer_count"] = len(r["prev_customers"])
        del r["cur_customers"]
        del r["prev_customers"]
        _add_diff_fields(r)
    return sorted(result.values(), key=lambda x: (-x["cur_amount"], x["pincode"]))


def _area_pincode_summary(data):
    pc = {}
    for r in data:
        p = r["pincode"]
        if p not in pc:
            pc[p] = {
                "pincode": p, "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0,
                "items": set(), "customers": set(),
            }
        for f in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "invoices"]:
            pc[p][f"cur_{f}"] += r[f"cur_{f}"]
            pc[p][f"prev_{f}"] += r[f"prev_{f}"]
        pc[p]["items"].add(r["item_name"])
        pc[p]["customers"].add(r.get("customer", ""))

    result = []
    for p, v in sorted(pc.items(), key=lambda x: -x[1]["cur_amount"]):
        v["item_count"] = len(v["items"])
        v["customer_count"] = len(v["customers"])
        del v["items"]
        del v["customers"]
        _add_diff_fields(v)
        result.append(v)
    return result


def _area_product_summary(data):
    pr = {}
    for r in data:
        item = r["item_name"]
        if item not in pr:
            pr[item] = {
                "item_name": item, "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0,
                "pincodes": set(),
            }
        for f in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "invoices"]:
            pr[item][f"cur_{f}"] += r[f"cur_{f}"]
            pr[item][f"prev_{f}"] += r[f"prev_{f}"]
        pr[item]["pincodes"].add(r["pincode"])

    result = []
    for item, v in sorted(pr.items(), key=lambda x: -x[1]["cur_amount"]):
        v["pincode_count"] = len(v["pincodes"])
        del v["pincodes"]
        _add_diff_fields(v)
        result.append(v)
    return result


def _area_charts(data):
    pc_amount = {}
    pc_pcs = {}
    item_amount = {}
    for r in data:
        p = r["pincode"]
        pc_amount[p] = pc_amount.get(p, 0) + r["cur_amount"]
        pc_pcs[p] = pc_pcs.get(p, 0) + r["cur_pcs"]
        i = r["item_name"]
        item_amount[i] = item_amount.get(i, 0) + r["cur_amount"]

    pc_labels = sorted(pc_amount, key=pc_amount.get, reverse=True)
    item_labels = sorted(item_amount, key=item_amount.get, reverse=True)

    return {
        "kpis": _build_kpis(data),
        "pincode_amount": {"labels": pc_labels, "values": [round(pc_amount[k], 2) for k in pc_labels]},
        "pincode_pcs": {"labels": pc_labels, "values": [round(pc_pcs.get(k, 0), 2) for k in pc_labels]},
        "item_amount": {"labels": item_labels, "values": [round(item_amount[k], 2) for k in item_labels]},
    }


# ═══════════════════════════════════════════════════════════════
# REPORT 3: SALES PERSON OVERDUE REPORT
# ═══════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_sp_overdue_report(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    period = filters.get("period", "custom")
    sales_persons = filters.get("sales_persons", [])
    companies = filters.get("companies", [])
    items = filters.get("items", [])

    if not from_date or not to_date:
        frappe.throw(_("From Date and To Date are required"))

    prev_from, prev_to = _get_previous_period(from_date, to_date, period)

    current_data = _overdue_query(from_date, to_date, sales_persons, companies, items)
    prev_data = _overdue_query(prev_from, prev_to, sales_persons, companies, items)

    merged = _overdue_merge(current_data, prev_data)

    return {
        "current_period": {"from_date": from_date, "to_date": to_date},
        "previous_period": {"from_date": prev_from, "to_date": prev_to},
        "data": merged,
        "summary": _overdue_summary(merged),
        "charts": _overdue_charts(merged),
    }


def _overdue_query(fd, td, sales_persons=None, companies=None, items=None):
    conditions = ["si.docstatus = 1", "si.fe_sales_person IS NOT NULL", "si.fe_sales_person != ''"]
    params = [fd, td]
    conditions.append("si.posting_date BETWEEN %s AND %s")

    if sales_persons:
        placeholders = ",".join(["%s"] * len(sales_persons))
        conditions.append(f"si.fe_sales_person IN ({placeholders})")
        params.extend(sales_persons)
    if companies:
        placeholders = ",".join(["%s"] * len(companies))
        conditions.append(f"si.company IN ({placeholders})")
        params.extend(companies)
    if items:
        placeholders = ",".join(["%s"] * len(items))
        conditions.append(f"sii.item_name IN ({placeholders})")
        params.extend(items)

    where_clause = " AND ".join(conditions)
    return frappe.db.sql(f"""
        SELECT
            si.fe_sales_person AS sales_person,
            si.customer,
            sii.item_name,
            si.company,
            si.name AS invoice_no,
            si.posting_date,
            si.due_date,
            COALESCE(si.outstanding_amount, 0) AS outstanding_amount,
            COALESCE(sii.fe_box, 0) AS box,
            COALESCE(sii.fe_pcs, 0) AS pcs,
            COALESCE(sii.fe_ltr, 0) AS ltr,
            sii.qty,
            sii.amount,
            si.grand_total,
            CASE
                WHEN si.due_date < CURDATE() AND si.outstanding_amount > 0
                THEN DATEDIFF(CURDATE(), si.due_date) ELSE 0
            END AS days_overdue
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE {where_clause}
        ORDER BY si.fe_sales_person, si.customer, si.posting_date
    """, params, as_dict=True)


def _overdue_merge(current, previous):
    result = {}
    for row in current:
        key = (row.sales_person, row.customer, row.invoice_no)
        if key not in result:
            result[key] = {
                "sales_person": row.sales_person, "customer": row.customer,
                "invoice_no": row.invoice_no, "company": row.company,
                "posting_date": str(row.posting_date)[:10] if row.posting_date else "",
                "due_date": str(row.due_date)[:10] if row.due_date else "",
                "days_overdue": row.days_overdue or 0,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_qty": 0,
                "cur_amount": 0, "cur_outstanding": 0, "cur_grand_total": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_qty": 0,
                "prev_amount": 0, "prev_outstanding": 0, "prev_grand_total": 0,
                "items": set(),
            }
        r = result[key]
        r["cur_box"] += flt(row.box)
        r["cur_pcs"] += flt(row.pcs)
        r["cur_ltr"] += flt(row.ltr)
        r["cur_qty"] += flt(row.qty)
        r["cur_amount"] += flt(row.amount)
        r["cur_outstanding"] += flt(row.outstanding_amount)
        r["cur_grand_total"] += flt(row.grand_total)
        r["items"].add(row.item_name)

    for row in previous:
        key = (row.sales_person, row.customer, row.invoice_no)
        if key not in result:
            result[key] = {
                "sales_person": row.sales_person, "customer": row.customer,
                "invoice_no": row.invoice_no, "company": row.company,
                "posting_date": str(row.posting_date)[:10] if row.posting_date else "",
                "due_date": str(row.due_date)[:10] if row.due_date else "",
                "days_overdue": row.days_overdue or 0,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_qty": 0,
                "cur_amount": 0, "cur_outstanding": 0, "cur_grand_total": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_qty": 0,
                "prev_amount": 0, "prev_outstanding": 0, "prev_grand_total": 0,
                "items": set(),
            }
        r = result[key]
        r["prev_box"] += flt(row.box)
        r["prev_pcs"] += flt(row.pcs)
        r["prev_ltr"] += flt(row.ltr)
        r["prev_qty"] += flt(row.qty)
        r["prev_amount"] += flt(row.amount)
        r["prev_outstanding"] += flt(row.outstanding_amount)
        r["prev_grand_total"] += flt(row.grand_total)

    for r in result.values():
        r["item_list"] = ", ".join(sorted(r["items"]))
        del r["items"]
        _add_diff_fields(r)
    return sorted(result.values(), key=lambda x: (-x["days_overdue"], -x["cur_outstanding"]))


def _overdue_summary(data):
    sp = {}
    for r in data:
        s = r["sales_person"]
        if s not in sp:
            sp[s] = {
                "sales_person": s, "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_outstanding": 0, "cur_grand_total": 0,
                "cur_invoices": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_qty": 0,
                "prev_amount": 0, "prev_outstanding": 0, "prev_grand_total": 0,
                "prev_invoices": 0,
                "customers": set(), "items": set(), "overdue_count": 0,
            }
        for f in ["box", "pcs", "ltr", "qty", "amount", "outstanding", "grand_total"]:
            sp[s][f"cur_{f}"] += r[f"cur_{f}"]
            sp[s][f"prev_{f}"] += r[f"prev_{f}"]
        sp[s]["cur_invoices"] += 1
        sp[s]["customers"].add(r["customer"])
        sp[s]["items"].add(r["item_list"])
        if r["cur_outstanding"] > 0:
            sp[s]["overdue_count"] += 1

    result = []
    for s, v in sorted(sp.items(), key=lambda x: -x[1]["cur_outstanding"]):
        v["customer_count"] = len(v["customers"])
        del v["customers"]
        del v["items"]
        _add_diff_fields(v)
        result.append(v)
    return result


def _overdue_charts(data):
    sp_outstanding = {}
    sp_amount = {}
    for r in data:
        s = r["sales_person"]
        sp_outstanding[s] = sp_outstanding.get(s, 0) + r["cur_outstanding"]
        sp_amount[s] = sp_amount.get(s, 0) + r["cur_amount"]

    sp_labels = sorted(sp_outstanding, key=sp_outstanding.get, reverse=True)
    return {
        "kpis": _build_kpis(data),
        "sp_outstanding": {"labels": sp_labels, "values": [round(sp_outstanding[k], 2) for k in sp_labels]},
        "sp_amount": {"labels": sp_labels, "values": [round(sp_amount.get(k, 0), 2) for k in sp_labels]},
    }


# ═══════════════════════════════════════════════════════════════
# REPORT 4: PARTY GROUP DETAILS
# ═══════════════════════════════════════════════════════════════

@frappe.whitelist()
def get_partygroup_report(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    period = filters.get("period", "custom")
    party_groups = filters.get("party_groups", [])
    companies = filters.get("companies", [])
    items = filters.get("items", [])

    if not from_date or not to_date:
        frappe.throw(_("From Date and To Date are required"))

    prev_from, prev_to = _get_previous_period(from_date, to_date, period)

    current_data = _partygroup_query(from_date, to_date, party_groups, companies, items)
    prev_data = _partygroup_query(prev_from, prev_to, party_groups, companies, items)

    merged = _partygroup_merge(current_data, prev_data)

    return {
        "current_period": {"from_date": from_date, "to_date": to_date},
        "previous_period": {"from_date": prev_from, "to_date": prev_to},
        "data": merged,
        "group_summary": _partygroup_group_summary(merged),
        "product_summary": _partygroup_product_summary(merged),
        "charts": _partygroup_charts(merged),
    }


def _partygroup_query(fd, td, party_groups=None, companies=None, items=None):
    conditions = ["si.docstatus = 1"]
    params = [fd, td]
    conditions.append("si.posting_date BETWEEN %s AND %s")

    if party_groups:
        placeholders = ",".join(["%s"] * len(party_groups))
        conditions.append(f"COALESCE(pg.name, 'No Group') IN ({placeholders})")
        params.extend(party_groups)
    if companies:
        placeholders = ",".join(["%s"] * len(companies))
        conditions.append(f"si.company IN ({placeholders})")
        params.extend(companies)
    if items:
        placeholders = ",".join(["%s"] * len(items))
        conditions.append(f"sii.item_name IN ({placeholders})")
        params.extend(items)

    where_clause = " AND ".join(conditions)
    return frappe.db.sql(f"""
        SELECT
            COALESCE(pg.name, 'No Group') AS party_group,
            si.customer,
            sii.item_name,
            si.company,
            si.name AS invoice_no,
            si.posting_date,
            COALESCE(si.outstanding_amount, 0) AS outstanding_amount,
            COALESCE(sii.fe_box, 0) AS box,
            COALESCE(sii.fe_pcs, 0) AS pcs,
            COALESCE(sii.fe_ltr, 0) AS ltr,
            COALESCE(sii.fe_total_ltr, 0) AS total_ltr,
            sii.qty,
            sii.rate,
            sii.amount,
            si.grand_total
        FROM `tabSales Invoice Item` sii
        INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
        LEFT JOIN `tabParty Group Party` pgp ON pgp.party = si.customer AND pgp.party_type = 'Customer'
        LEFT JOIN `tabParty Group` pg ON pg.name = pgp.parent
        WHERE {where_clause}
        ORDER BY party_group, si.customer, sii.item_name
    """, params, as_dict=True)


def _partygroup_merge(current, previous):
    result = {}
    for row in current:
        key = (row.party_group, row.customer, row.item_name)
        if key not in result:
            result[key] = {
                "party_group": row.party_group, "customer": row.customer,
                "item_name": row.item_name,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0, "cur_outstanding": 0,
                "cur_grand_total": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0, "prev_outstanding": 0,
                "prev_grand_total": 0,
            }
        r = result[key]
        r["cur_box"] += flt(row.box)
        r["cur_pcs"] += flt(row.pcs)
        r["cur_ltr"] += flt(row.ltr)
        r["cur_total_ltr"] += flt(row.total_ltr)
        r["cur_qty"] += flt(row.qty)
        r["cur_amount"] += flt(row.amount)
        r["cur_invoices"] += 1
        r["cur_outstanding"] += flt(row.outstanding_amount)
        r["cur_grand_total"] += flt(row.grand_total)

    for row in previous:
        key = (row.party_group, row.customer, row.item_name)
        if key not in result:
            result[key] = {
                "party_group": row.party_group, "customer": row.customer,
                "item_name": row.item_name,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0, "cur_outstanding": 0,
                "cur_grand_total": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0, "prev_outstanding": 0,
                "prev_grand_total": 0,
            }
        r = result[key]
        r["prev_box"] += flt(row.box)
        r["prev_pcs"] += flt(row.pcs)
        r["prev_ltr"] += flt(row.ltr)
        r["prev_total_ltr"] += flt(row.total_ltr)
        r["prev_qty"] += flt(row.qty)
        r["prev_amount"] += flt(row.amount)
        r["prev_invoices"] += 1
        r["prev_outstanding"] += flt(row.outstanding_amount)
        r["prev_grand_total"] += flt(row.grand_total)

    for r in result.values():
        _add_diff_fields(r)
    return sorted(result.values(), key=lambda x: (-x["cur_amount"], x["party_group"]))


def _partygroup_group_summary(data):
    pg = {}
    for r in data:
        g = r["party_group"]
        if g not in pg:
            pg[g] = {
                "party_group": g, "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0, "cur_outstanding": 0,
                "cur_grand_total": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0, "prev_outstanding": 0,
                "prev_grand_total": 0,
                "customers": set(), "items": set(),
            }
        for f in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "invoices", "outstanding", "grand_total"]:
            pg[g][f"cur_{f}"] += r[f"cur_{f}"]
            pg[g][f"prev_{f}"] += r[f"prev_{f}"]
        pg[g]["customers"].add(r["customer"])
        pg[g]["items"].add(r["item_name"])

    result = []
    for g, v in sorted(pg.items(), key=lambda x: -x[1]["cur_amount"]):
        v["customer_count"] = len(v["customers"])
        v["item_count"] = len(v["items"])
        del v["customers"]
        del v["items"]
        _add_diff_fields(v)
        result.append(v)
    return result


def _partygroup_product_summary(data):
    pr = {}
    for r in data:
        item = r["item_name"]
        if item not in pr:
            pr[item] = {
                "item_name": item, "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0,
                "groups": set(),
            }
        for f in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "invoices"]:
            pr[item][f"cur_{f}"] += r[f"cur_{f}"]
            pr[item][f"prev_{f}"] += r[f"prev_{f}"]
        pr[item]["groups"].add(r["party_group"])

    result = []
    for item, v in sorted(pr.items(), key=lambda x: -x[1]["cur_amount"]):
        v["group_count"] = len(v["groups"])
        del v["groups"]
        _add_diff_fields(v)
        result.append(v)
    return result


def _partygroup_charts(data):
    pg_amount = {}
    pg_customers = {}
    item_amount = {}
    for r in data:
        g = r["party_group"]
        pg_amount[g] = pg_amount.get(g, 0) + r["cur_amount"]
        if g not in pg_customers:
            pg_customers[g] = set()
        pg_customers[g].add(r["customer"])
        i = r["item_name"]
        item_amount[i] = item_amount.get(i, 0) + r["cur_amount"]

    pg_labels = sorted(pg_amount, key=pg_amount.get, reverse=True)
    item_labels = sorted(item_amount, key=item_amount.get, reverse=True)

    return {
        "kpis": _build_kpis(data),
        "group_amount": {"labels": pg_labels, "values": [round(pg_amount[k], 2) for k in pg_labels]},
        "group_customers": {"labels": pg_labels, "values": [len(pg_customers.get(k, set())) for k in pg_labels]},
        "item_amount": {"labels": item_labels, "values": [round(item_amount[k], 2) for k in item_labels]},
    }
