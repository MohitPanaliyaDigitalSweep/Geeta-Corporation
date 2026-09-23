import json

import frappe
from frappe import _
from frappe.utils import flt, getdate


@frappe.whitelist()
def get_pending_invoices(company, party_type, party):
    """All unpaid invoices of a party, oldest first.

    party_type: 'Customer' (Sales Invoice) or 'Supplier' (Purchase Invoice).
    """
    if party_type not in ("Customer", "Supplier"):
        return []
    doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
    party_field = "customer" if party_type == "Customer" else "supplier"

    invoices = frappe.get_all(
        doctype,
        filters={"company": company, party_field: party, "docstatus": 1, "outstanding_amount": [">", 0.01]},
        fields=["name", "posting_date", "due_date", "grand_total", "outstanding_amount"],
        order_by="posting_date asc, name asc",
    )

    total = sum(flt(i.outstanding_amount) for i in invoices)
    return {"invoices": invoices, "total_outstanding": total}


@frappe.whitelist()
def create_bulk_payment(company, party_type, party, amount, mode_of_payment=None,
                        posting_date=None, reference_no=None, reference_date=None):
    """Create one Payment Entry against all pending invoices of a party.

    Allocation: oldest invoices are paid in full first; the next oldest is
    partially paid with whatever remains; newer invoices are left untouched.

    Returns the created Payment Entry, the allocation, and any excess amount.
    """
    if party_type not in ("Customer", "Supplier"):
        frappe.throw(_("Party Type must be Customer or Supplier"))
    if not company or not party:
        frappe.throw(_("Company and Party are required"))

    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Amount must be greater than 0"))

    pending = get_pending_invoices(company, party_type, party)
    invoices = pending["invoices"]
    if not invoices:
        frappe.throw(_("No pending invoices for this party"))

    total_outstanding = flt(pending["total_outstanding"])
    if amount > total_outstanding + 0.01:
        frappe.throw(
            _("Amount {0} exceeds total outstanding {1}. Reduce the amount.").format(
                frappe.format(amount, "Currency"), frappe.format(total_outstanding, "Currency")
            )
        )

    # Allocate oldest -> newest: full for old invoices, partial on the next
    allocation = []
    remaining = amount
    for inv in invoices:
        if remaining <= 0.01:
            break
        alloc = min(flt(inv.outstanding_amount), remaining)
        allocation.append({
            "name": inv.name,
            "posting_date": inv.posting_date,
            "grand_total": flt(inv.grand_total),
            "outstanding_amount": flt(inv.outstanding_amount),
            "allocated_amount": alloc,
            "fully_paid": alloc >= flt(inv.outstanding_amount) - 0.01,
        })
        remaining -= alloc

    excess = remaining  # money that could not be allocated (should be ~0 given the guard above)

    payment_type = "Receive" if party_type == "Customer" else "Pay"
    pe = frappe.new_doc("Payment Entry")
    pe.company = company
    pe.payment_type = payment_type
    pe.party_type = party_type
    pe.party = party
    pe.posting_date = posting_date or frappe.utils.today()
    pe.mode_of_payment = mode_of_payment or _default_mode_of_payment(company)
    pe.paid_amount = amount
    pe.received_amount = amount
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.reference_no = reference_no
    pe.reference_date = reference_date or pe.posting_date
    pe.remarks = "Bulk payment via Fast Entry"

    default_bank = frappe.db.get_value("Company", company, "default_bank_account") or _first_bank_account(company)
    if not default_bank:
        frappe.throw(_("No Bank Account found for company {0}. Set a default bank account.").format(company))

    if payment_type == "Pay":
        default_payable = frappe.db.get_value("Company", company, "default_payable_account") or _first_account(company, "Payable")
        pe.paid_from = default_bank
        pe.paid_to = default_payable
    else:
        default_receivable = frappe.db.get_value("Company", company, "default_receivable_account") or _first_account(company, "Receivable")
        pe.paid_from = default_receivable
        pe.paid_to = default_bank

    for row in allocation:
        pe.append("references", {
            "reference_doctype": "Sales Invoice" if party_type == "Customer" else "Purchase Invoice",
            "reference_name": row["name"],
            "total_amount": row["grand_total"],
            "outstanding_amount": row["outstanding_amount"],
            "allocated_amount": row["allocated_amount"],
        })

    pe.flags.ignore_permissions = True
    pe.flags.ignore_links = True
    pe.save(ignore_permissions=True)
    pe.submit()

    return {
        "name": pe.name,
        "payment_type": payment_type,
        "allocation": allocation,
        "excess": excess,
        "amount": amount,
    }


def _default_mode_of_payment(company):
    mop = frappe.db.get_value("Mode of Payment", {"type": "Bank", "enabled": 1}, "name")
    if mop:
        return mop
    mop = frappe.db.get_value("Mode of Payment", {"enabled": 1}, "name")
    if mop:
        return mop
    return "Wire Transfer"


def _first_bank_account(company):
    acc = frappe.db.get_value("Account", {"company": company, "account_type": "Bank", "is_group": 0}, "name")
    if acc:
        return acc
    return frappe.db.get_value("Account", {"company": company, "account_type": "Bank"}, "name")


def _first_account(company, account_type):
    return frappe.db.get_value(
        "Account",
        {"company": company, "account_type": account_type, "is_group": 0},
        "name",
    )


@frappe.whitelist()
def get_pending_purchase_invoices(company, supplier):
    """Pending Purchase Invoices of a supplier plus every supplier sharing its
    payment group (fe_group, e.g. all IOCL accounts treated as one)."""
    if not company or not supplier:
        return {"suppliers": [], "invoices": [], "total_outstanding": 0, "group": ""}

    # First try fe_group field on supplier, then fallback to Party Group Party table
    group_name = frappe.db.get_value("Supplier", supplier, "fe_group") or ""
    if not group_name:
        pgp = frappe.db.get_value("Party Group Party", {"party_type": "Supplier", "party": supplier}, "parent")
        if pgp:
            group_name = pgp

    suppliers = [{"name": supplier, "supplier_name": frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier}]
    if group_name:
        # Get all suppliers in the same Party Group
        members = frappe.get_all(
            "Party Group Party",
            filters={"parent": group_name, "party_type": "Supplier", "party": ["!=", supplier]},
            fields=["party as name", "party_name"],
        )
        suppliers += members

    names = [s["name"] for s in suppliers]
    invoices = frappe.get_all(
        "Purchase Invoice",
        filters={"company": company, "supplier": ["in", names], "docstatus": 1, "outstanding_amount": [">", 0.01]},
        fields=["name", "supplier", "posting_date", "due_date", "grand_total", "outstanding_amount"],
        order_by="posting_date asc, name asc",
    )
    name_to_supplier = {s["name"]: s.get("supplier_name") or s["name"] for s in suppliers}
    for inv in invoices:
        inv["supplier_name"] = name_to_supplier.get(inv.supplier) or inv.supplier

    total = sum(flt(i.outstanding_amount) for i in invoices)
    return {"suppliers": suppliers, "invoices": invoices, "total_outstanding": total, "group": group_name}


@frappe.whitelist()
def create_bulk_supplier_payment(data):
    """Create Payment Entries for selected Purchase Invoices (full or partial per
    invoice, via checkboxes). One Payment Entry per supplier, so grouped
    suppliers (fe_group) are paid in a single action.

    data = {
        company, posting_date, mode_of_payment, reference_no, reference_date,
        items: [{name (Purchase Invoice), supplier, pay_amount}]
    }
    """
    if isinstance(data, str):
        data = json.loads(data)

    company = data.get("company")
    raw_items = data.get("items") or []
    if not company or not raw_items:
        frappe.throw(_("Company and at least one selected invoice are required"))

    validated = []
    for it in raw_items:
        pay_amount = flt(it.get("pay_amount"))
        if pay_amount <= 0.01:
            continue
        pi = frappe.db.get_value(
            "Purchase Invoice",
            it.get("name"),
            ["supplier", "grand_total", "outstanding_amount", "docstatus"],
            as_dict=True,
        )
        if not pi or pi.docstatus != 1:
            frappe.throw(_("Invoice {0} is not a submitted Purchase Invoice").format(it.get("name")))
        if pi.supplier != it.get("supplier"):
            frappe.throw(_("Invoice {0} does not belong to supplier {1}").format(it.get("name"), it.get("supplier")))
        if pay_amount > flt(pi.outstanding_amount) + 0.01:
            frappe.throw(
                _("Payment for {0} (Rs. {1}) exceeds its outstanding amount (Rs. {2})").format(
                    it.get("name"), pay_amount, pi.outstanding_amount
                )
            )
        validated.append({
            "name": it.get("name"),
            "supplier": pi.supplier,
            "pay_amount": pay_amount,
            "grand_total": flt(pi.grand_total),
            "outstanding_amount": flt(pi.outstanding_amount),
        })

    if not validated:
        frappe.throw(_("No invoices selected for payment"))

    by_supplier = {}
    for v in validated:
        by_supplier.setdefault(v["supplier"], []).append(v)

    payments = []
    for supplier, rows in by_supplier.items():
        pe = _make_supplier_payment(company, supplier, rows, data)
        payments.append({
            "supplier": supplier,
            "supplier_name": frappe.db.get_value("Supplier", supplier, "supplier_name") or supplier,
            "payment_entry": pe.name,
            "amount": pe.paid_amount,
        })

    return {
        "payments": payments,
        "count": len(payments),
        "total": sum(flt(p["amount"]) for p in payments),
    }


def _make_supplier_payment(company, supplier, rows, data):
    total = sum(flt(r["pay_amount"]) for r in rows)

    pe = frappe.new_doc("Payment Entry")
    pe.company = company
    pe.payment_type = "Pay"
    pe.party_type = "Supplier"
    pe.party = supplier
    pe.posting_date = getdate(data.get("posting_date")) or frappe.utils.today()
    pe.mode_of_payment = data.get("mode_of_payment") or _default_mode_of_payment(company)
    pe.paid_amount = total
    pe.received_amount = total
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.reference_no = data.get("reference_no") or ("BULK-" + frappe.generate_hash(5).upper())
    pe.reference_date = getdate(data.get("reference_date")) or pe.posting_date
    pe.remarks = "Bulk supplier payment via Fast Entry"

    default_bank = frappe.db.get_value("Company", company, "default_bank_account") or _first_bank_account(company)
    if not default_bank:
        frappe.throw(_("No Bank Account found for company {0}. Set a default bank account.").format(company))

    pe.paid_from = default_bank
    pe.paid_to = _supplier_payable_account(company, supplier)

    for r in rows:
        pe.append("references", {
            "reference_doctype": "Purchase Invoice",
            "reference_name": r["name"],
            "total_amount": r["grand_total"],
            "outstanding_amount": r["outstanding_amount"],
            "allocated_amount": r["pay_amount"],
        })

    pe.flags.ignore_permissions = True
    pe.flags.ignore_links = True
    pe.save(ignore_permissions=True)
    pe.submit()
    return pe


def _supplier_payable_account(company, supplier):
    """Supplier-specific payable account (Party Account child) else company default."""
    acc = frappe.db.get_value(
        "Party Account",
        {"parenttype": "Supplier", "parent": supplier, "company": company},
        "account",
    )
    if acc:
        return acc
    return frappe.db.get_value("Company", company, "default_payable_account") or _first_account(company, "Payable")


@frappe.whitelist()
def get_pending_sales_invoices(company, customer):
    """Pending Sales Invoices of a customer plus every customer sharing its
    payment group (fe_group), oldest first."""
    if not company or not customer:
        return {"customers": [], "invoices": [], "total_outstanding": 0, "group": ""}

    # First try fe_group field on customer, then fallback to Party Group Party table
    group_name = frappe.db.get_value("Customer", customer, "fe_group") or ""
    if not group_name:
        pgp = frappe.db.get_value("Party Group Party", {"party_type": "Customer", "party": customer}, "parent")
        if pgp:
            group_name = pgp

    customers = [{"name": customer, "customer_name": frappe.db.get_value("Customer", customer, "customer_name") or customer}]
    if group_name:
        # Get all customers in the same Party Group
        members = frappe.get_all(
            "Party Group Party",
            filters={"parent": group_name, "party_type": "Customer", "party": ["!=", customer]},
            fields=["party as name", "party_name"],
        )
        customers += members

    names = [c["name"] for c in customers]
    invoices = frappe.get_all(
        "Sales Invoice",
        filters={"company": company, "customer": ["in", names], "docstatus": 1, "outstanding_amount": [">", 0.01]},
        fields=["name", "customer", "posting_date", "due_date", "grand_total", "outstanding_amount"],
        order_by="posting_date asc, name asc",
    )
    name_to_customer = {c["name"]: c.get("customer_name") or c["name"] for c in customers}
    for inv in invoices:
        inv["customer_name"] = name_to_customer.get(inv.customer) or inv.customer

    total = sum(flt(i.outstanding_amount) for i in invoices)
    return {"customers": customers, "invoices": invoices, "total_outstanding": total, "group": group_name}


@frappe.whitelist()
def create_bulk_customer_payment(data):
    """Create Payment Entries (Receive) for selected Sales Invoices (full or
    partial per invoice). One Payment Entry per customer, so grouped customers
    (fe_group) are collected in a single action.

    data = {
        company, posting_date, mode_of_payment, reference_no, reference_date,
        items: [{name (Sales Invoice), customer, pay_amount}]
    }
    """
    if isinstance(data, str):
        data = json.loads(data)

    company = data.get("company")
    raw_items = data.get("items") or []
    if not company or not raw_items:
        frappe.throw(_("Company and at least one selected invoice are required"))

    validated = []
    for it in raw_items:
        pay_amount = flt(it.get("pay_amount"))
        if pay_amount <= 0.01:
            continue
        si = frappe.db.get_value(
            "Sales Invoice",
            it.get("name"),
            ["customer", "grand_total", "outstanding_amount", "docstatus"],
            as_dict=True,
        )
        if not si or si.docstatus != 1:
            frappe.throw(_("Invoice {0} is not a submitted Sales Invoice").format(it.get("name")))
        if si.customer != it.get("customer"):
            frappe.throw(_("Invoice {0} does not belong to customer {1}").format(it.get("name"), it.get("customer")))
        if pay_amount > flt(si.outstanding_amount) + 0.01:
            frappe.throw(
                _("Payment for {0} (Rs. {1}) exceeds its outstanding amount (Rs. {2})").format(
                    it.get("name"), pay_amount, si.outstanding_amount
                )
            )
        validated.append({
            "name": it.get("name"),
            "customer": si.customer,
            "pay_amount": pay_amount,
            "grand_total": flt(si.grand_total),
            "outstanding_amount": flt(si.outstanding_amount),
        })

    if not validated:
        frappe.throw(_("No invoices selected for payment"))

    by_customer = {}
    for v in validated:
        by_customer.setdefault(v["customer"], []).append(v)

    payments = []
    for customer, rows in by_customer.items():
        pe = _make_customer_payment(company, customer, rows, data)
        payments.append({
            "customer": customer,
            "customer_name": frappe.db.get_value("Customer", customer, "customer_name") or customer,
            "payment_entry": pe.name,
            "amount": pe.paid_amount,
        })

    return {
        "payments": payments,
        "count": len(payments),
        "total": sum(flt(p["amount"]) for p in payments),
    }


def _make_customer_payment(company, customer, rows, data):
    total = sum(flt(r["pay_amount"]) for r in rows)

    pe = frappe.new_doc("Payment Entry")
    pe.company = company
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = customer
    pe.posting_date = getdate(data.get("posting_date")) or frappe.utils.today()
    pe.mode_of_payment = data.get("mode_of_payment") or _default_mode_of_payment(company)
    pe.paid_amount = total
    pe.received_amount = total
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.reference_no = data.get("reference_no") or ("BULK-" + frappe.generate_hash(5).upper())
    pe.reference_date = getdate(data.get("reference_date")) or pe.posting_date
    pe.remarks = "Bulk customer payment via Fast Entry"

    default_bank = frappe.db.get_value("Company", company, "default_bank_account") or _first_bank_account(company)
    if not default_bank:
        frappe.throw(_("No Bank Account found for company {0}. Set a default bank account.").format(company))

    default_receivable = frappe.db.get_value("Company", company, "default_receivable_account") or _first_account(company, "Receivable")
    pe.paid_from = default_receivable
    pe.paid_to = default_bank

    for r in rows:
        pe.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": r["name"],
            "total_amount": r["grand_total"],
            "outstanding_amount": r["outstanding_amount"],
            "allocated_amount": r["pay_amount"],
        })

    pe.flags.ignore_permissions = True
    pe.flags.ignore_links = True
    pe.save(ignore_permissions=True)
    pe.submit()
    return pe