import frappe
from datetime import date, timedelta

from frappe.utils import flt, getdate, add_months, cstr

MONTH_KEYS = [
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
]


@frappe.whitelist()
def get_ledger(company, from_date, to_date, party_type=None, party=None, account=None):
    """Party / account ledger via the ERPNext General Ledger engine.

    party/account can be exact docname or partial text (resolved via LIKE match).
    Returns columns and rows (decorative Total/separator rows removed).
    """
    from erpnext.accounts.report.general_ledger.general_ledger import execute as gl_execute

    filters = frappe._dict({
        "company": company,
        "from_date": from_date,
        "to_date": to_date,
        "group_by": "Group by Voucher",
        "show_opening_entries": 1,
    })

    if party_type:
        filters.party_type = party_type

    if party:
        resolved = _resolve_party(party_type, party)
        if resolved:
            filters.party = resolved
        else:
            return {"columns": [], "rows": []}

    if account:
        resolved = _resolve_account(company, account)
        if resolved:
            filters.account = resolved
        else:
            return {"columns": [], "rows": []}

    try:
        columns, rows = gl_execute(filters)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "fast_entry GL error")
        return {"columns": [], "rows": []}

    result = []
    for r in rows:
        account = (r.get("account") or "").strip("'\" ")
        if account == "Total":
            continue
        if r.get("posting_date") is None and account != "Opening" and r.get("voucher_type") is None:
            continue
        result.append(r)

    return {
        "columns": [{"fieldname": c.get("fieldname"), "label": c.get("label")} for c in columns],
        "rows": result,
    }


def _resolve_party(party_type, search):
    """Resolve partial party text to list of exact matching names.

    Searches both Customer and Supplier if party_type is not set.
    """
    if party_type and party_type not in ("Customer", "Supplier"):
        return [search]

    doctypes = [party_type] if party_type else ["Customer", "Supplier"]
    result = []
    for dt in doctypes:
        name_field = "customer_name" if dt == "Customer" else "supplier_name"
        matches = frappe.get_list(
            dt,
            filters={"disabled": 0},
            or_filters=[
                ["name", "like", f"%{search}%"],
                [name_field, "like", f"%{search}%"],
            ],
            fields=["name"],
            limit_page_length=50,
            order_by="name asc",
        )
        result.extend(m.name for m in matches)
    return result


def _resolve_account(company, search):
    """Resolve partial account text to list of exact matching names."""
    matches = frappe.get_list(
        "Account",
        filters={"company": company, "is_group": 0},
        or_filters=[
            ["name", "like", f"%{search}%"],
            ["account_name", "like", f"%{search}%"],
        ],
        fields=["name", "account_name"],
        limit_page_length=50,
        order_by="name asc",
    )
    return [m.name for m in matches]


@frappe.whitelist()
def search_accounts(company, search, limit=15):
    """Search leaf accounts by name for a company."""
    limit = int(limit)
    matches = frappe.get_list(
        "Account",
        filters={"company": company, "is_group": 0},
        or_filters=[
            ["name", "like", f"%{search}%"],
            ["account_name", "like", f"%{search}%"],
        ],
        fields=["name", "account_name"],
        limit_page_length=limit,
        order_by="name asc",
    )
    return matches


@frappe.whitelist()
def get_pnl(company, from_date, to_date, period="year"):
    """Profit & Loss from the full Chart of Accounts, bucketed by period.

    Every Income/Expense account (leaf AND group, zero or not) is listed with
    detailed per-period values rolled up from GL entries, so newly created
    accounts always appear. Net profit = income − expense, computed purely
    from these COA rows.

    period: "month" (%Y-%m), "year" (%Y) or "week" (ISO %Y-%W, Monday start).
    """
    from_date, to_date = getdate(from_date), getdate(to_date)
    if period not in ("month", "year", "week"):
        period = "year"

    if period == "month":
        bucket_sql = "DATE_FORMAT(gl.posting_date, '%%Y-%%m')"
    elif period == "year":
        bucket_sql = "DATE_FORMAT(gl.posting_date, '%%Y')"
    else:
        bucket_sql = "DATE_FORMAT(gl.posting_date, '%%Y-%%u')"

    # Account tree (the WHOLE Income/Expense COA, groups included)
    all_accounts = frappe.db.sql(
        """
        SELECT name, parent_account, root_type, account_name, is_group
        FROM `tabAccount`
        WHERE company = %s AND root_type IN ('Income', 'Expense')
        """,
        (company,),
        as_dict=True,
    )
    by_name = {a.name: a for a in all_accounts}
    children = {}
    for a in all_accounts:
        children.setdefault(a.parent_account or "", []).append(a)
    for kids in children.values():
        kids.sort(key=lambda a: a.name)

    # GL amounts per account per bucket (%% escaped: frappe.db.sql applies %
    # formatting with the query parameters)
    gl_rows = frappe.db.sql(
        """
        SELECT a.name AS account,
               {bucket} AS bucket,
               a.root_type,
               SUM(gl.debit) AS debit,
               SUM(gl.credit) AS credit
        FROM `tabGL Entry` gl
        JOIN `tabAccount` a ON a.name = gl.account
        WHERE gl.company = %s AND gl.is_cancelled = 0
          AND gl.posting_date BETWEEN %s AND %s
          AND a.root_type IN ('Income', 'Expense')
        GROUP BY gl.account, {bucket}
        """.replace("{bucket}", bucket_sql),
        (company, from_date, to_date),
        as_dict=True,
    )

    # own[account][bucket] = signed amount (positive = income direction)
    own = {}
    buckets = set()
    for r in gl_rows:
        buckets.add(r.bucket)
        amount = (flt(r.credit) - flt(r.debit)) if r.root_type == "Income" else (flt(r.debit) - flt(r.credit))
        own.setdefault(r.account, {})[r.bucket] = amount

    # Period axis: every bucket inside the range, even with no postings, so
    # columns are stable. Derived from the date range (not just posted data).
    period_keys = _period_axis(from_date, to_date, period, buckets)

    memo = {}

    def compute(account):
        """Return {bucket: amount} for an account including its subtree."""
        if account in memo:
            return memo[account]
        totals = dict(own.get(account, {}))
        for child in children.get(account, []):
            child_totals = compute(child.name)
            for k, v in child_totals.items():
                totals[k] = flt(totals.get(k)) + flt(v)
        memo[account] = totals
        return totals

    def emit(rows, account, indent):
        """Append a group row (with subtree subtotal) or leaf row. Groups
        always render, even at zero, so the full COA stays visible."""
        a = by_name[account]
        totals = compute(account)
        rows.append({
            "name": account,
            "root_type": a.root_type,
            "indent": indent,
            "is_group": bool(a.is_group),
            "periods": {k: flt(totals.get(k)) for k in period_keys},
            "total": sum(flt(totals.get(k)) for k in period_keys),
        })
        if a.is_group:
            for child in children.get(account, []):
                emit(rows, child.name, indent + 1)

    income_rows = []
    expense_rows = []
    for root_child in children.get("", []):
        target = income_rows if root_child.root_type == "Income" else expense_rows
        emit(target, root_child.name, 0)

    # Totals over TOP-LEVEL rows only (their subtotals already include children)
    top = [r for r in income_rows if r["indent"] == 0]
    income_total = sum(flt(r["total"]) for r in top)
    top = [r for r in expense_rows if r["indent"] == 0]
    expense_total = sum(flt(r["total"]) for r in top)
    net = income_total - expense_total

    if period == "month":
        period_labels = {k: f"{MONTH_KEYS[int(k[5:7]) - 1]} {k[:4]}" for k in period_keys}
    elif period == "year":
        period_labels = {k: k for k in period_keys}
    else:
        period_labels = {}
        for k in period_keys:
            y, w = k.split("-")
            monday = date(int(y), 1, 4) + timedelta(weeks=int(w) - 1) - timedelta(days=date(int(y), 1, 4).isoweekday() - 1)
            period_labels[k] = "W%s (%s)" % (w.lstrip("0") or "0", monday.strftime("%d %b"))

    return {
        "period": period,
        "periods": period_keys,
        "period_labels": period_labels,
        "rows": income_rows + expense_rows,
        "income_total": income_total,
        "expense_total": expense_total,
        "net_profit": net,
    }


def _period_axis(from_date, to_date, period, buckets):
    """Chronological bucket keys covering the range (stable columns)."""
    if period == "month":
        keys, m = [], from_date.replace(day=1)
        while m <= to_date:
            keys.append(cstr(m)[:7])
            m = add_months(m, 1)
        return keys
    if period == "year":
        return [str(y) for y in range(from_date.year, to_date.year + 1)]
    # week: every ISO week touching the range
    keys = []
    seen = set()
    d = from_date
    one_day = timedelta(days=1)
    while d <= to_date:
        iso_y, iso_w, _ = d.isocalendar()
        k = "%d-%02d" % (iso_y, iso_w)
        if k not in seen:
            seen.add(k)
            keys.append(k)
        d += one_day
    # include posted buckets outside walk (defensive; same sort order)
    for k in sorted(buckets):
        if k not in seen:
            seen.add(k)
            keys.append(k)
    return sorted(keys)




@frappe.whitelist()
def search_parties(party_type, search, limit=15):
    """Search customers or suppliers by name.

    Partial search: 'IOCL' matches 'IOCL - Ahmedabad', 'IOCL - Mumbai', etc.
    """
    if party_type not in ("Customer", "Supplier"):
        return []
    limit = int(limit)
    name_field = "customer_name" if party_type == "Customer" else "supplier_name"
    parties = frappe.get_list(
        party_type,
        filters={"disabled": 0},
        or_filters=[
            ["name", "like", f"%{search}%"],
            [name_field, "like", f"%{search}%"],
        ],
        fields=["name", name_field],
        limit_page_length=limit,
        order_by="name asc",
    )
    for p in parties:
        p["full_name"] = p.get(name_field) or p["name"]
    return parties


@frappe.whitelist()
def search_all_parties(search, limit=15):
    """Search both Customer and Supplier by name, no party_type required."""
    limit = int(limit)
    result = []
    for dt, nf in [("Customer", "customer_name"), ("Supplier", "supplier_name")]:
        parties = frappe.get_list(
            dt,
            filters={"disabled": 0},
            or_filters=[
                ["name", "like", f"%{search}%"],
                [nf, "like", f"%{search}%"],
            ],
            fields=["name", nf],
            limit_page_length=limit,
            order_by="name asc",
        )
        for p in parties:
            result.append({
                "name": p.name,
                "full_name": p.get(nf) or p.name,
                "party_type": dt,
            })
    result.sort(key=lambda x: x["name"])
    return result[:limit]