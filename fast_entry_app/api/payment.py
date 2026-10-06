import json

import frappe
from frappe import _
from frappe.utils import flt, getdate


def _group_of_party(party_type, party):
    """Kept as the local name; resolution itself lives in party_group so the
    payment, party-search and UI paths cannot disagree about who is grouped."""
    from fast_entry_app.api.party_group import resolve_group

    return resolve_group(party_type, party)


def _display_name(party_type, party):
    field = "customer_name" if party_type == "Customer" else "supplier_name"
    return frappe.db.get_value(party_type, party, field) or party


def _party_ref(party_type, party):
    return {"name": party, "party_name": _display_name(party_type, party), "party_type": party_type}


def _group_members(party_type, group):
    """Every party in a group as [{name, party_name, party_type}]."""
    if not group:
        return []
    members = frappe.get_all(
        "Party Group Party",
        filters={"parent": group, "party_type": party_type},
        fields=["party as name", "party_name"],
        order_by="idx asc",
    )
    for m in members:
        m["party_name"] = m.get("party_name") or _display_name(party_type, m["name"])
        m["party_type"] = party_type
    return members


def _assert_group_serves(party_type, group):
    """Refuse a group whose group_type does not include this party type."""
    group_type = frappe.db.get_value("Party Group", group, "group_type")
    if group_type and group_type != "Both" and group_type != party_type:
        frappe.throw(
            _("Party Group {0} is for {1}, not {2}").format(group, group_type, party_type)
        )


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
    payment group (fe_group / Party Group), e.g. all IOCL accounts as one."""
    return _pending_grouped_invoices(company, "Supplier", supplier)


def _pending_grouped_invoices(company, party_type, party):
    """Pending invoices of one party expanded across its whole group.

    Shared by the supplier and customer variants, which were byte-identical
    apart from the doctype and party field.
    """
    if not company or not party:
        return {"parties": [], "invoices": [], "total_outstanding": 0, "group": ""}

    doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
    party_field = "customer" if party_type == "Customer" else "supplier"

    group_name = _group_of_party(party_type, party)

    parties = [_party_ref(party_type, party)]
    if group_name:
        parties += [m for m in _group_members(party_type, group_name) if m["name"] != party]

    names = [p["name"] for p in parties]
    invoices = frappe.get_all(
        doctype,
        filters={"company": company, party_field: ["in", names], "docstatus": 1, "outstanding_amount": [">", 0.01]},
        fields=["name", party_field, "posting_date", "due_date", "grand_total", "outstanding_amount"],
        order_by="posting_date asc, name asc",
    )
    name_to_party = {p["name"]: p["party_name"] for p in parties}
    for inv in invoices:
        inv["party_name"] = name_to_party.get(inv.get(party_field)) or inv.get(party_field)

    total = sum(flt(i.outstanding_amount) for i in invoices)

    # Per-member subtotals, so group mode can show what each member owes before
    # the run happens rather than only the group total.
    by_party = {}
    for inv in invoices:
        key = inv.get(party_field)
        entry = by_party.setdefault(key, {"party": key, "party_name": inv["party_name"],
                                          "party_type": party_type, "invoices": [], "total": 0.0})
        entry["invoices"].append(inv)
        entry["total"] += flt(inv.outstanding_amount)

    return {
        "parties": parties,
        "party_names": names,
        "invoices": invoices,
        "by_party": by_party,
        "total_outstanding": total,
        "group": group_name,
    }


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
    pe.remarks = data.get("remarks") or "Bulk supplier payment via Fast Entry"

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
    payment group (fe_group / Party Group), oldest first."""
    return _pending_grouped_invoices(company, "Customer", customer)


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
    pe.remarks = data.get("remarks") or "Bulk customer payment via Fast Entry"

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

@frappe.whitelist()
def search_payment_parties(party_type, search=None, limit=40):
    """Mixed dropdown source for the payment pages: individual parties AND the
    groups they belong to, in one list.

    Both appear because the operator's intent differs. A party means "settle
    this one account"; a group means "clear the whole group in one action". The
    group row is what makes a group-wide payment one click rather than a manual
    walk down the member list.

    Returns [{kind: "party"|"group", name, label, group, member_count}].
    """
    if party_type not in ("Customer", "Supplier"):
        frappe.throw(_("Party Type must be Customer or Supplier"))

    search = (search or "").strip()
    like = f"%{search}%"
    field = "customer_name" if party_type == "Customer" else "supplier_name"

    parties = frappe.get_all(
        party_type,
        filters={"name": ["like", like], field: ["like", like]} if search else {},
        fields=["name", field + " as party_name"],
        order_by=field + " asc",
        limit_page_length=limit,
    )
    for p in parties:
        p["kind"] = "party"
        p["label"] = p.get("party_name") or p["name"]
        p["party_name"] = p["label"]
        p["group"] = _group_of_party(party_type, p["name"])
        p["member_count"] = 0

    groups = frappe.get_all(
        "Party Group",
        filters={"group_name": ["like", like]} if search else {},
        fields=["name", "group_name", "group_type"],
        order_by="group_name asc",
        limit_page_length=limit,
    )
    out = []
    for g in groups:
        members = _group_members(party_type, g["name"])
        if not members:
            continue
        out.append({
            "kind": "group",
            "name": g["name"],
            "label": g.get("group_name") or g["name"],
            "group": g["name"],
            "group_type": g.get("group_type"),
            "member_count": len(members),
        })

    return {"parties": parties, "groups": out, "results": parties + out}


@frappe.whitelist()
def get_pending_party_group_invoices(company, party_type, group):
    """Every pending invoice of every member of a Party Group.

    The group-wide counterpart of get_pending_invoices: where that one answers
    "what is this party owed", this answers "what does the whole group owe".
    """
    if party_type not in ("Customer", "Supplier"):
        frappe.throw(_("Party Type must be Customer or Supplier"))
    if not group:
        frappe.throw(_("Party Group is required"))
    _assert_group_serves(party_type, group)

    members = _group_members(party_type, group)
    if not members:
        frappe.throw(_("Party Group {0} has no {1} members").format(group, party_type))

    result = _pending_grouped_invoices(company, party_type, members[0]["name"])
    # The shared helper keys off the first member's group, so trust the group
    # we were asked about rather than a group's fe_group round trip.
    result["group"] = group
    return result


@frappe.whitelist()
def create_party_group_payment(data):
    """Pay a whole Party Group in one action.

    Creates one Payment Entry per member party (an ERPNext Payment Entry holds a
    single party, so N members necessarily mean N Payment Entries) and then
    records the run as a single submitted Party Group Payment, which is the
    only place that says these N entries were one decision for one amount.

    data = {
        company, party_type, group, posting_date, mode_of_payment,
        reference_no, reference_date, remarks,
        items: [{party, pay_amount, invoices: [{name, pay_amount}]}]
    }
    """
    if isinstance(data, str):
        data = json.loads(data)

    company = data.get("company")
    party_type = data.get("party_type")
    group = data.get("group")
    raw_items = data.get("items") or []

    if party_type not in ("Customer", "Supplier"):
        frappe.throw(_("Party Type must be Customer or Supplier"))
    if not company or not group or not raw_items:
        frappe.throw(_("Company, Party Group and at least one member payment are required"))
    _assert_group_serves(party_type, group)

    invoice_doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
    party_field = "customer" if party_type == "Customer" else "supplier"
    members = {m["name"]: m for m in _group_members(party_type, group)}
    if not members:
        frappe.throw(_("Party Group {0} has no {1} members").format(group, party_type))

    prepared = []
    for it in raw_items:
        party = it.get("party")
        if not party:
            frappe.throw(_("Every row needs a party"))
        if party not in members:
            frappe.throw(_("{0} is not a member of group {1}").format(party, group))

        rows = []
        for ref in (it.get("invoices") or []):
            pay_amount = flt(ref.get("pay_amount"))
            if pay_amount <= 0.01:
                continue
            inv = frappe.db.get_value(
                invoice_doctype,
                ref.get("name"),
                [party_field, "grand_total", "outstanding_amount", "docstatus"],
                as_dict=True,
            )
            if not inv or inv.docstatus != 1:
                frappe.throw(_("Invoice {0} is not a submitted {1}").format(ref.get("name"), invoice_doctype))
            if inv.get(party_field) != party:
                frappe.throw(_("Invoice {0} does not belong to {1}").format(ref.get("name"), party))
            if pay_amount > flt(inv.outstanding_amount) + 0.01:
                frappe.throw(
                    _("Payment for {0} (Rs. {1}) exceeds its outstanding amount (Rs. {2})").format(
                        ref.get("name"), pay_amount, inv.outstanding_amount
                    )
                )
            rows.append({
                "name": ref.get("name"),
                "pay_amount": pay_amount,
                "grand_total": flt(inv.grand_total),
                "outstanding_amount": flt(inv.outstanding_amount),
            })

        declared = flt(it.get("pay_amount"))
        if rows:
            row_total = sum(flt(r["pay_amount"]) for r in rows)
            # A row total that disagrees with the invoice lines is the classic
            # cause of a half-paid invoice, so reconcile rather than guess.
            if declared and abs(declared - row_total) > 0.01:
                frappe.throw(
                    _("{0}: total Rs. {1} does not match its invoices (Rs. {2})").format(party, declared, row_total)
                )
            paid = row_total
        elif declared > 0.01:
            # No invoices ticked: pay the party as an advance/on-account.
            paid = declared
        else:
            continue

        prepared.append({
            "party": party,
            "party_name": members[party]["party_name"],
            "rows": rows,
            "pay_amount": paid,
            "outstanding_before": sum(flt(r["outstanding_amount"]) for r in rows),
            "invoice_count": len(rows),
        })

    if not prepared:
        frappe.throw(_("Nothing to pay for group {0}").format(group))

    shared = dict(data)
    shared["remarks"] = data.get("remarks") or "Group payment for {0} via Fast Entry".format(group)

    payments = []
    for p in prepared:
        if p["rows"]:
            maker = _make_customer_payment if party_type == "Customer" else _make_supplier_payment
            pe = maker(company, p["party"], p["rows"], shared)
        else:
            pe = _make_advance_payment(company, party_type, p["party"], p["pay_amount"], shared)
        payments.append({
            "party": p["party"],
            "party_name": p["party_name"],
            "payment_entry": pe.name,
            "paid_amount": flt(pe.paid_amount),
            "invoice_count": p["invoice_count"],
            "outstanding_before": p["outstanding_before"],
        })

    pgp = frappe.new_doc("Party Group Payment")
    # Read the series off the DocType instead of repeating the literal here:
    # a hardcoded copy silently drifts and Frappe falls back to a hash name.
    _series_field = frappe.get_meta("Party Group Payment").get_field("naming_series")
    pgp.naming_series = ((_series_field.options or "").split("\n")[0].strip() or "PGP-#####")
    pgp.party_type = party_type
    pgp.group = group
    pgp.company = company
    pgp.posting_date = getdate(data.get("posting_date")) or frappe.utils.today()
    pgp.mode_of_payment = data.get("mode_of_payment") or _default_mode_of_payment(company)
    pgp.reference_no = data.get("reference_no")
    pgp.reference_date = getdate(data.get("reference_date"))
    pgp.remarks = shared["remarks"]
    for p in payments:
        pgp.append("payments", {
            "party_type": party_type,
            "party": p["party"],
            "party_name": p["party_name"],
            "payment_entry": p["payment_entry"],
            "invoice_count": p["invoice_count"],
            "outstanding": p["outstanding_before"],
            "paid_amount": p["paid_amount"],
        })
    pgp.flags.ignore_permissions = True
    pgp.insert(ignore_permissions=True)
    pgp.submit()

    return {
        "name": pgp.name,
        "group": group,
        "group_name": pgp.group_name,
        "party_type": party_type,
        "total": flt(pgp.total_amount),
        "payment_entries": [p["payment_entry"] for p in payments],
        "payments": payments,
    }


def _make_advance_payment(company, party_type, party, amount, data):
    """Payment Entry with no invoice references - settles an account without
    touching any invoice (advance / on-account)."""
    if amount <= 0:
        frappe.throw(_("Amount must be greater than 0"))

    pe = frappe.new_doc("Payment Entry")
    pe.company = company
    pe.payment_type = "Receive" if party_type == "Customer" else "Pay"
    pe.party_type = party_type
    pe.party = party
    pe.posting_date = getdate(data.get("posting_date")) or frappe.utils.today()
    pe.mode_of_payment = data.get("mode_of_payment") or _default_mode_of_payment(company)
    pe.paid_amount = flt(amount)
    pe.received_amount = flt(amount)
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.reference_no = data.get("reference_no") or ("ADV-" + frappe.generate_hash(5).upper())
    pe.reference_date = getdate(data.get("reference_date")) or pe.posting_date
    pe.remarks = data.get("remarks") or "Advance payment via Fast Entry"

    default_bank = frappe.db.get_value("Company", company, "default_bank_account") or _first_bank_account(company)
    if not default_bank:
        frappe.throw(_("No Bank Account found for company {0}. Set a default bank account.").format(company))

    # Mirrors _make_supplier_payment / _make_customer_payment exactly: for a
    # Receive money flows Receivable -> Bank, for a Pay it flows Bank -> Payable.
    # The party-bearing Receivable/Payable account must never be the Bank side,
    # or GL validation throws "Party Type and Party can only be set for
    # Receivable / Payable account".
    if party_type == "Customer":
        pe.paid_from = frappe.db.get_value("Company", company, "default_receivable_account") or _first_account(company, "Receivable")
        pe.paid_to = default_bank
    else:
        pe.paid_from = default_bank
        pe.paid_to = _supplier_payable_account(company, party)

    pe.flags.ignore_permissions = True
    pe.save(ignore_permissions=True)
    pe.submit()
    return pe
