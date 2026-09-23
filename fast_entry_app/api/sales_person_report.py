import json
import frappe
from frappe import _
from frappe.utils import flt, getdate, add_months, add_days, date_diff


@frappe.whitelist()
def get_sales_person_performance(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)

    filters = filters or {}
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    period = filters.get("period", "custom")
    sales_person = filters.get("sales_person")
    company = filters.get("company")
    customer = filters.get("customer")
    party_group = filters.get("party_group")
    item_code = filters.get("item_code")
    pincode = filters.get("pincode")

    if not from_date or not to_date:
        frappe.throw(_("From Date and To Date are required"))

    current_data = _get_performance_data(from_date, to_date, sales_person, company, customer, party_group, item_code, pincode)
    prev_from, prev_to = _get_previous_period(from_date, to_date, period)
    prev_data = _get_performance_data(prev_from, prev_to, sales_person, company, customer, party_group, item_code, pincode)

    result = _merge_periods(current_data, prev_data)

    return {
        "current_period": {"from_date": from_date, "to_date": to_date},
        "previous_period": {"from_date": prev_from, "to_date": prev_to},
        "data": result,
        "summary": _calculate_summary(result),
        "pincode_summary": _calculate_pincode_summary(result),
        "sp_pincode_summary": _calculate_sp_pincode_summary(result),
        "charts": _calculate_charts(result, current_data, from_date, to_date),
    }


def _get_performance_data(from_date, to_date, sales_person=None, company=None, customer=None, party_group=None, item_code=None, pincode=None):
    conditions = ["si.docstatus = 1", "si.fe_sales_person IS NOT NULL", "si.fe_sales_person != ''"]
    params = [from_date, to_date]
    conditions.append("si.posting_date BETWEEN %s AND %s")

    if sales_person:
        conditions.append("si.fe_sales_person = %s")
        params.append(sales_person)
    if company:
        conditions.append("si.company = %s")
        params.append(company)
    if customer:
        conditions.append("si.customer = %s")
        params.append(customer)
    if party_group:
        conditions.append("c.fe_group = %s")
        params.append(party_group)
    if item_code:
        conditions.append("sii.item_name = %s")
        params.append(item_code)
    if pincode:
        conditions.append("addr.pincode = %s")
        params.append(pincode)

    where_clause = " AND ".join(conditions)

    rows = frappe.db.sql(f"""
        SELECT
            si.fe_sales_person AS sales_person,
            si.customer,
            COALESCE(c.fe_group, '') AS party_group,
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
        LEFT JOIN `tabCustomer` c ON c.name = si.customer
        LEFT JOIN `tabAddress` addr ON addr.name = si.customer_address
        WHERE {where_clause}
        ORDER BY si.fe_sales_person, addr.pincode, si.customer, sii.item_name, si.posting_date
    """, params, as_dict=True)

    return rows


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


def _merge_periods(current, previous):
    result = {}

    def _init_row(row):
        return {
            "sales_person": row.sales_person,
            "customer": row.customer,
            "party_group": row.party_group,
            "pincode": row.pincode,
            "item_name": row.item_name,
            "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
            "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0, "cur_grand_total": 0,
            "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
            "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0, "prev_grand_total": 0,
        }

    for row in current:
        key = (row.sales_person, row.customer, row.party_group, row.pincode, row.item_name)
        if key not in result:
            result[key] = _init_row(row)
        r = result[key]
        r["cur_box"] += flt(row.box)
        r["cur_pcs"] += flt(row.pcs)
        r["cur_ltr"] += flt(row.ltr)
        r["cur_total_ltr"] += flt(row.total_ltr)
        r["cur_qty"] += flt(row.qty)
        r["cur_amount"] += flt(row.amount)
        r["cur_grand_total"] += flt(row.grand_total)
        r["cur_invoices"] += 1

    for row in previous:
        key = (row.sales_person, row.customer, row.party_group, row.pincode, row.item_name)
        if key not in result:
            result[key] = _init_row(row)
        r = result[key]
        r["prev_box"] += flt(row.box)
        r["prev_pcs"] += flt(row.pcs)
        r["prev_ltr"] += flt(row.ltr)
        r["prev_total_ltr"] += flt(row.total_ltr)
        r["prev_qty"] += flt(row.qty)
        r["prev_amount"] += flt(row.amount)
        r["prev_grand_total"] += flt(row.grand_total)
        r["prev_invoices"] += 1

    for key, r in result.items():
        for field in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "grand_total"]:
            cur = r[f"cur_{field}"]
            prev = r[f"prev_{field}"]
            diff = cur - prev
            pct = (diff / prev * 100) if prev else (100 if cur else 0)
            r[f"diff_{field}"] = diff
            r[f"pct_{field}"] = round(pct, 1)
        r["diff_invoices"] = r["cur_invoices"] - r["prev_invoices"]

    return sorted(result.values(), key=lambda x: (-x["cur_amount"], x["sales_person"]))


def _calculate_summary(data):
    summary = {}
    for row in data:
        sp = row["sales_person"]
        if sp not in summary:
            summary[sp] = {
                "sales_person": sp,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0, "cur_grand_total": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0, "prev_grand_total": 0,
                "customers": set(), "items": set(), "pincodes": set(),
            }
        s = summary[sp]
        for field in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "invoices", "grand_total"]:
            s[f"cur_{field}"] += row[f"cur_{field}"]
            s[f"prev_{field}"] += row[f"prev_{field}"]
        s["customers"].add(row["customer"])
        s["items"].add(row["item_name"])
        if row.get("pincode"):
            s["pincodes"].add(row["pincode"])

    result = []
    for sp, s in sorted(summary.items(), key=lambda x: (-x[1]["cur_amount"])):
        s["customers"] = len(s["customers"])
        s["items"] = len(s["items"])
        s["pincode_count"] = len(s["pincodes"])
        del s["pincodes"]
        _add_diff_fields(s)
        result.append(s)

    return result


def _calculate_pincode_summary(data):
    summary = {}
    for row in data:
        pc = row["pincode"] or "No Pincode"
        if pc not in summary:
            summary[pc] = {
                "pincode": pc,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0, "cur_grand_total": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0, "prev_grand_total": 0,
                "sales_persons": set(), "customers": set(), "items": set(),
            }
        s = summary[pc]
        for field in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "invoices", "grand_total"]:
            s[f"cur_{field}"] += row[f"cur_{field}"]
            s[f"prev_{field}"] += row[f"prev_{field}"]
        s["sales_persons"].add(row["sales_person"])
        s["customers"].add(row["customer"])
        s["items"].add(row["item_name"])

    result = []
    for pc, s in sorted(summary.items(), key=lambda x: (-x[1]["cur_amount"])):
        s["sales_person_count"] = len(s["sales_persons"])
        s["customer_count"] = len(s["customers"])
        s["item_count"] = len(s["items"])
        del s["sales_persons"]
        del s["customers"]
        del s["items"]
        _add_diff_fields(s)
        result.append(s)

    return result


def _calculate_sp_pincode_summary(data):
    summary = {}
    for row in data:
        sp = row["sales_person"]
        pc = row["pincode"] or "No Pincode"
        key = (sp, pc)
        if key not in summary:
            summary[key] = {
                "sales_person": sp,
                "pincode": pc,
                "cur_box": 0, "cur_pcs": 0, "cur_ltr": 0, "cur_total_ltr": 0,
                "cur_qty": 0, "cur_amount": 0, "cur_invoices": 0, "cur_grand_total": 0,
                "prev_box": 0, "prev_pcs": 0, "prev_ltr": 0, "prev_total_ltr": 0,
                "prev_qty": 0, "prev_amount": 0, "prev_invoices": 0, "prev_grand_total": 0,
                "customers": set(), "items": set(),
            }
        s = summary[key]
        for field in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "invoices", "grand_total"]:
            s[f"cur_{field}"] += row[f"cur_{field}"]
            s[f"prev_{field}"] += row[f"prev_{field}"]
        s["customers"].add(row["customer"])
        s["items"].add(row["item_name"])

    result = []
    for (sp, pc), s in sorted(summary.items(), key=lambda x: (-x[1]["cur_amount"], x[0][0])):
        s["customer_count"] = len(s["customers"])
        s["item_count"] = len(s["items"])
        del s["customers"]
        del s["items"]
        _add_diff_fields(s)
        result.append(s)

    return result


def _add_diff_fields(s):
    for field in ["box", "pcs", "ltr", "total_ltr", "qty", "amount", "grand_total"]:
        cur = s[f"cur_{field}"]
        prev = s[f"prev_{field}"]
        diff = cur - prev
        pct = (diff / prev * 100) if prev else (100 if cur else 0)
        s[f"diff_{field}"] = diff
        s[f"pct_{field}"] = round(pct, 1)
    s["diff_invoices"] = s["cur_invoices"] - s["prev_invoices"]


def _calculate_charts(data, current_data, from_date, to_date):
    """Build chart-ready data structures."""
    # 1. Sales by Sales Person (donut)
    sp_amounts = {}
    sp_pcs = {}
    for r in data:
        sp = r["sales_person"]
        sp_amounts[sp] = sp_amounts.get(sp, 0) + r["cur_amount"]
        sp_pcs[sp] = sp_pcs.get(sp, 0) + r["cur_pcs"]

    sp_labels = sorted(sp_amounts, key=sp_amounts.get, reverse=True)
    sp_chart = {
        "labels": sp_labels,
        "values": [round(sp_amounts[k], 2) for k in sp_labels],
    }
    sp_pcs_chart = {
        "labels": sp_labels,
        "values": [round(sp_pcs[k], 2) for k in sp_labels],
    }

    # 2. Sales by Pincode (bar)
    pc_amounts = {}
    pc_qty = {}
    for r in data:
        pc = r["pincode"] or "No Pincode"
        pc_amounts[pc] = pc_amounts.get(pc, 0) + r["cur_amount"]
        pc_qty[pc] = pc_qty.get(pc, 0) + r["cur_pcs"]

    pc_labels = sorted(pc_amounts, key=pc_amounts.get, reverse=True)
    pc_chart = {
        "labels": pc_labels,
        "amounts": [round(pc_amounts[k], 2) for k in pc_labels],
        "qty": [round(pc_qty[k], 2) for k in pc_labels],
    }

    # 3. Sales by Item (horizontal bar)
    item_amounts = {}
    item_qty = {}
    for r in data:
        ic = r["item_name"]
        item_amounts[ic] = item_amounts.get(ic, 0) + r["cur_amount"]
        item_qty[ic] = item_qty.get(ic, 0) + r["cur_pcs"]

    item_labels = sorted(item_amounts, key=item_amounts.get, reverse=True)
    item_chart = {
        "labels": item_labels,
        "amounts": [round(item_amounts[k], 2) for k in item_labels],
        "qty": [round(item_qty[k], 2) for k in item_labels],
    }

    # 4. Period comparison (grouped bar: current vs previous)
    sp_cur = {}
    sp_prev = {}
    for r in data:
        sp = r["sales_person"]
        sp_cur[sp] = sp_cur.get(sp, 0) + r["cur_amount"]
        sp_prev[sp] = sp_prev.get(sp, 0) + r["prev_amount"]

    period_chart = {
        "labels": sp_labels,
        "current": [round(sp_cur.get(k, 0), 2) for k in sp_labels],
        "previous": [round(sp_prev.get(k, 0), 2) for k in sp_labels],
    }

    # 5. Monthly trend (daily aggregation from raw current data)
    daily = {}
    for r in current_data:
        dt = str(r.get("posting_date", ""))[:10]
        if dt:
            daily[dt] = daily.get(dt, 0) + flt(r.amount)

    daily_labels = sorted(daily.keys())
    trend_chart = {
        "labels": daily_labels,
        "values": [round(daily[k], 2) for k in daily_labels],
    }

    # 6. KPI summary
    total_cur_amount = sum(r["cur_amount"] for r in data)
    total_prev_amount = sum(r["prev_amount"] for r in data)
    total_cur_invoices = sum(r["cur_invoices"] for r in data)
    total_prev_invoices = sum(r["prev_invoices"] for r in data)
    total_cur_pcs = sum(r["cur_pcs"] for r in data)
    total_prev_pcs = sum(r["prev_pcs"] for r in data)
    total_cur_box = sum(r["cur_box"] for r in data)
    total_prev_box = sum(r["prev_box"] for r in data)
    total_cur_ltr = sum(r["cur_ltr"] for r in data)
    total_prev_ltr = sum(r["prev_ltr"] for r in data)

    avg_order = total_cur_amount / total_cur_invoices if total_cur_invoices else 0
    prev_avg_order = total_prev_amount / total_prev_invoices if total_prev_invoices else 0

    kpis = {
        "total_amount": {"cur": round(total_cur_amount, 2), "prev": round(total_prev_amount, 2)},
        "total_invoices": {"cur": total_cur_invoices, "prev": total_prev_invoices},
        "avg_order": {"cur": round(avg_order, 2), "prev": round(prev_avg_order, 2)},
        "total_pcs": {"cur": round(total_cur_pcs, 2), "prev": round(total_prev_pcs, 2)},
        "total_box": {"cur": round(total_cur_box, 2), "prev": round(total_prev_box, 2)},
        "total_ltr": {"cur": round(total_cur_ltr, 2), "prev": round(total_prev_ltr, 2)},
    }

    return {
        "kpis": kpis,
        "sp_amount": sp_chart,
        "sp_pcs": sp_pcs_chart,
        "pincode": pc_chart,
        "items": item_chart,
        "period_comparison": period_chart,
        "trend": trend_chart,
    }


@frappe.whitelist()
def get_filter_options():
    sales_persons = frappe.get_all("Sales Person", filters={"enabled": 1}, pluck="name")
    companies = frappe.get_all("Company", pluck="name")
    customers = frappe.db.sql(
        "SELECT DISTINCT si.customer FROM `tabSales Invoice` si WHERE si.docstatus = 1 AND si.customer IS NOT NULL ORDER BY si.customer",
        pluck=True,
    )
    party_groups = frappe.db.sql(
        "SELECT DISTINCT fe_group FROM `tabCustomer` WHERE fe_group IS NOT NULL AND fe_group != '' ORDER BY fe_group",
        pluck=True,
    )
    items = frappe.db.sql(
        "SELECT DISTINCT sii.item_name FROM `tabSales Invoice Item` sii INNER JOIN `tabSales Invoice` si ON si.name = sii.parent WHERE si.docstatus = 1 AND sii.item_name IS NOT NULL AND sii.item_name != '' ORDER BY sii.item_name",
        pluck=True,
    )
    pincodes = frappe.db.sql(
        "SELECT DISTINCT addr.pincode FROM `tabAddress` addr WHERE addr.pincode IS NOT NULL AND addr.pincode != '' ORDER BY addr.pincode",
        pluck=True,
    )

    return {
        "sales_persons": sales_persons,
        "companies": companies,
        "customers": customers,
        "party_groups": party_groups,
        "items": items,
        "pincodes": pincodes,
    }
