import frappe
from frappe import _
from frappe.utils import flt, nowdate, getdate


@frappe.whitelist()
def get_party_bills_summary(company, party_type="Customer", search=""):
    """Get all parties with pending invoices for a company, with overdue summary.

    Returns list of {party, party_name, total_outstanding, overdue_amount,
    invoice_count, oldest_due_date, invoices: [...]}
    """
    if party_type not in ("Customer", "Supplier"):
        frappe.throw(_("Party Type must be Customer or Supplier"))

    doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
    party_field = "customer" if party_type == "Customer" else "supplier"

    # Get all unpaid invoices grouped by party
    invoices = frappe.get_all(
        doctype,
        filters={"company": company, "docstatus": 1, "outstanding_amount": [">", 0.01]},
        fields=["name", party_field, "posting_date", "due_date", "grand_total", "outstanding_amount"],
        order_by=f"{party_field} asc, posting_date asc",
    )

    # Group by party
    parties = {}
    for inv in invoices:
        p = inv.get(party_field)
        if search and search.lower() not in (p or "").lower():
            # Also check party name
            pname = frappe.db.get_value(
                "Customer" if party_type == "Customer" else "Supplier", p,
                "customer_name" if party_type == "Customer" else "supplier_name"
            ) or p
            if search.lower() not in (pname or "").lower():
                continue
        if p not in parties:
            parties[p] = {
                "party": p,
                "party_name": frappe.db.get_value(
                    "Customer" if party_type == "Customer" else "Supplier", p,
                    "customer_name" if party_type == "Customer" else "supplier_name"
                ) or p,
                "invoices": [],
                "total_outstanding": 0,
                "overdue_amount": 0,
                "invoice_count": 0,
                "oldest_due_date": None,
            }
        parties[p]["invoices"].append({
            "name": inv.name,
            "posting_date": str(inv.posting_date),
            "due_date": str(inv.due_date) if inv.due_date else None,
            "grand_total": flt(inv.grand_total),
            "outstanding_amount": flt(inv.outstanding_amount),
            "is_overdue": bool(inv.due_date and getdate(inv.due_date) < getdate(nowdate())),
        })
        parties[p]["total_outstanding"] += flt(inv.outstanding_amount)
        parties[p]["invoice_count"] += 1
        if inv.due_date and getdate(inv.due_date) < getdate(nowdate()):
            parties[p]["overdue_amount"] += flt(inv.outstanding_amount)
        if parties[p]["oldest_due_date"] is None or (inv.due_date and getdate(inv.due_date) < getdate(parties[p]["oldest_due_date"])):
            parties[p]["oldest_due_date"] = str(inv.due_date) if inv.due_date else None

    # Sort by total_outstanding desc
    result = sorted(parties.values(), key=lambda x: x["total_outstanding"], reverse=True)
    for p in result:
        p["total_outstanding"] = round(p["total_outstanding"], 2)
        p["overdue_amount"] = round(p["overdue_amount"], 2)

    return result


@frappe.whitelist()
def get_party_overdue_summary(company, party_type="Customer"):
    """Get overdue summary: total overdue, number of overdue invoices, top overdue parties."""
    if party_type not in ("Customer", "Supplier"):
        frappe.throw(_("Party Type must be Customer or Supplier"))

    doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
    party_field = "customer" if party_type == "Customer" else "supplier"
    today = getdate(nowdate())

    invoices = frappe.get_all(
        doctype,
        filters={"company": company, "docstatus": 1, "outstanding_amount": [">", 0.01]},
        fields=[party_field, "due_date", "outstanding_amount"],
    )

    total_overdue = 0
    overdue_count = 0
    total_outstanding = 0
    for inv in invoices:
        total_outstanding += flt(inv.outstanding_amount)
        if inv.due_date and getdate(inv.due_date) < today:
            total_overdue += flt(inv.outstanding_amount)
            overdue_count += 1

    return {
        "total_outstanding": round(total_outstanding, 2),
        "total_overdue": round(total_overdue, 2),
        "overdue_count": overdue_count,
        "total_invoices": len(invoices),
    }