import json

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_party_groups(group_type=None):
    """List all Party Groups, optionally filtered by type."""
    filters = {}
    if group_type:
        filters["group_type"] = group_type

    groups = frappe.get_all(
        "Party Group",
        filters=filters,
        fields=["name", "group_name", "group_type", "description"],
        order_by="group_name asc",
    )

    for g in groups:
        g["party_count"] = frappe.db.count("Party Group Party", {"parent": g.name})

    return groups


@frappe.whitelist()
def create_party_group(data):
    """Create or update a Party Group with parties."""
    if isinstance(data, str):
        data = json.loads(data)

    group_name = data.get("group_name", "").strip()
    if not group_name:
        frappe.throw(_("Group Name is required"))

    # Use explicit existing_name if provided, otherwise lookup by group_name
    existing = data.get("existing_name") or frappe.db.get_value("Party Group", {"group_name": group_name}, "name")

    if existing:
        doc = frappe.get_doc("Party Group", existing)
        # Clear fe_group on old parties before removing them
        for old_row in doc.parties:
            if old_row.party and frappe.db.exists(old_row.party_type, old_row.party):
                frappe.db.set_value(old_row.party_type, old_row.party, "fe_group", None, update_modified=False)
        doc.group_type = data.get("group_type", doc.group_type)
        doc.description = data.get("description", doc.description)
        doc.parties = []
    else:
        doc = frappe.get_doc({
            "doctype": "Party Group",
            "group_name": group_name,
            "group_type": data.get("group_type", "Supplier"),
            "description": data.get("description", ""),
        })

    for p in data.get("parties", []):
        party_type = p.get("party_type")
        party = p.get("party")
        if not party_type or not party:
            continue

        # Auto-fill party_name and gstin
        party_doc = frappe.get_doc(party_type, party)
        doc.append("parties", {
            "party_type": party_type,
            "party": party,
            "party_name": party_doc.name,
            "gstin": getattr(party_doc, "gstin", None) or "",
        })

    if existing:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)

    # Set fe_group on all parties in this group
    for row in doc.parties:
        if row.party and frappe.db.exists(row.party_type, row.party):
            frappe.db.set_value(row.party_type, row.party, "fe_group", doc.name, update_modified=False)

    frappe.db.commit()
    return {"name": doc.name, "group_name": doc.group_name}


@frappe.whitelist()
def delete_party_group(name):
    """Delete a Party Group and unlink all parties."""
    if not frappe.db.exists("Party Group", name):
        frappe.throw(_("Party Group {0} not found").format(name))

    # Clear fe_group on all linked suppliers/customers
    suppliers = frappe.get_all("Party Group Party",
                               filters={"parent": name, "party_type": "Supplier"},
                               fields=["party"])
    for s in suppliers:
        frappe.db.set_value("Supplier", s.party, "fe_group", None, update_modified=False)

    customers = frappe.get_all("Party Group Party",
                               filters={"parent": name, "party_type": "Customer"},
                               fields=["party"])
    for c in customers:
        frappe.db.set_value("Customer", c.party, "fe_group", None, update_modified=False)

    frappe.delete_doc("Party Group", name, ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}


@frappe.whitelist()
def get_group_parties(group_name):
    """Get all parties in a group."""
    if not frappe.db.exists("Party Group", group_name):
        frappe.throw(_("Party Group {0} not found").format(group_name))

    parties = frappe.get_all(
        "Party Group Party",
        filters={"parent": group_name},
        fields=["party_type", "party", "party_name", "gstin"],
    )
    return parties


@frappe.whitelist()
def get_group_pending_invoices(company, group_name):
    """Fetch pending invoices for all parties in a group."""
    if not company or not group_name:
        return {"invoices": [], "total_outstanding": 0, "by_party": {}}

    group = frappe.get_doc("Party Group", group_name)
    if not group:
        frappe.throw(_("Party Group {0} not found").format(group_name))

    party_map = {}  # party_name -> party_type
    for row in group.parties:
        party_map[row.party] = row.party_type

    if not party_map:
        return {"invoices": [], "total_outstanding": 0, "by_party": {}}

    invoices = []
    by_party = {}

    # Fetch Supplier invoices (Purchase Invoices)
    supplier_names = [p for p, t in party_map.items() if t == "Supplier"]
    if supplier_names:
        pi_invoices = frappe.get_all(
            "Purchase Invoice",
            filters={
                "company": company,
                "supplier": ["in", supplier_names],
                "docstatus": 1,
                "outstanding_amount": [">", 0.01],
            },
            fields=["name", "supplier", "posting_date", "due_date", "grand_total", "outstanding_amount"],
            order_by="posting_date asc, name asc",
        )
        for inv in pi_invoices:
            inv["party_type"] = "Supplier"
            inv["party_name"] = frappe.db.get_value("Supplier", inv.supplier, "supplier_name") or inv.supplier
            invoices.append(inv)
            by_party.setdefault(inv.supplier, {"party_type": "Supplier", "invoices": [], "total": 0})
            by_party[inv.supplier]["invoices"].append(inv)
            by_party[inv.supplier]["total"] += flt(inv.outstanding_amount)

    # Fetch Customer invoices (Sales Invoices)
    customer_names = [p for p, t in party_map.items() if t == "Customer"]
    if customer_names:
        si_invoices = frappe.get_all(
            "Sales Invoice",
            filters={
                "company": company,
                "customer": ["in", customer_names],
                "docstatus": 1,
                "outstanding_amount": [">", 0.01],
            },
            fields=["name", "customer", "posting_date", "due_date", "grand_total", "outstanding_amount"],
            order_by="posting_date asc, name asc",
        )
        for inv in si_invoices:
            inv["party_type"] = "Customer"
            inv["party_name"] = frappe.db.get_value("Customer", inv.customer, "customer_name") or inv.customer
            inv["supplier"] = inv.customer  # alias for frontend compatibility
            invoices.append(inv)
            by_party.setdefault(inv.customer, {"party_type": "Customer", "invoices": [], "total": 0})
            by_party[inv.customer]["invoices"].append(inv)
            by_party[inv.customer]["total"] += flt(inv.outstanding_amount)

    total = sum(flt(i.outstanding_amount) for i in invoices)
    return {"invoices": invoices, "total_outstanding": total, "by_party": by_party}


@frappe.whitelist()
def create_group_payment(data):
    """Create Payment Entries for all selected invoices in a group.

    data = {
        company, posting_date, mode_of_payment, reference_no, reference_date,
        items: [{name, party_type, party, pay_amount}]
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

        party_type = it.get("party_type")
        party = it.get("party")
        inv_name = it.get("name")

        if party_type == "Supplier":
            pi = frappe.db.get_value(
                "Purchase Invoice", inv_name,
                ["supplier", "grand_total", "outstanding_amount", "docstatus"],
                as_dict=True,
            )
            if not pi or pi.docstatus != 1:
                frappe.throw(_("Invoice {0} is not a submitted Purchase Invoice").format(inv_name))
            if pay_amount > flt(pi.outstanding_amount) + 0.01:
                frappe.throw(_("Payment for {0} exceeds outstanding amount").format(inv_name))
            validated.append({
                "name": inv_name,
                "party_type": "Supplier",
                "party": pi.supplier,
                "pay_amount": pay_amount,
                "grand_total": flt(pi.grand_total),
                "outstanding_amount": flt(pi.outstanding_amount),
            })
        elif party_type == "Customer":
            si = frappe.db.get_value(
                "Sales Invoice", inv_name,
                ["customer", "grand_total", "outstanding_amount", "docstatus"],
                as_dict=True,
            )
            if not si or si.docstatus != 1:
                frappe.throw(_("Invoice {0} is not a submitted Sales Invoice").format(inv_name))
            if pay_amount > flt(si.outstanding_amount) + 0.01:
                frappe.throw(_("Payment for {0} exceeds outstanding amount").format(inv_name))
            validated.append({
                "name": inv_name,
                "party_type": "Customer",
                "party": si.customer,
                "pay_amount": pay_amount,
                "grand_total": flt(si.grand_total),
                "outstanding_amount": flt(si.outstanding_amount),
            })

    if not validated:
        frappe.throw(_("No invoices selected for payment"))

    # Group by party
    by_party = {}
    for v in validated:
        key = (v["party_type"], v["party"])
        by_party.setdefault(key, []).append(v)

    payments = []
    for (party_type, party), rows in by_party.items():
        pe = _make_party_payment(company, party_type, party, rows, data)
        payments.append({
            "party_type": party_type,
            "party": party,
            "party_name": frappe.db.get_value(party_type, party, f"{party.lower()}_name") or party,
            "payment_entry": pe.name,
            "amount": pe.paid_amount,
        })

    frappe.db.commit()
    return {
        "payments": payments,
        "count": len(payments),
        "total": sum(flt(p["amount"]) for p in payments),
    }


def _make_party_payment(company, party_type, party, rows, data):
    """Create a single Payment Entry for a party."""
    total = sum(flt(r["pay_amount"]) for r in rows)
    payment_type = "Receive" if party_type == "Customer" else "Pay"
    ref_doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"

    pe = frappe.new_doc("Payment Entry")
    pe.company = company
    pe.payment_type = payment_type
    pe.party_type = party_type
    pe.party = party
    pe.posting_date = data.get("posting_date") or frappe.utils.today()
    pe.mode_of_payment = data.get("mode_of_payment") or _default_mode_of_payment(company)
    pe.paid_amount = total
    pe.received_amount = total
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.reference_no = data.get("reference_no") or ("GRP-" + frappe.generate_hash(5).upper())
    pe.reference_date = data.get("reference_date") or pe.posting_date
    pe.remarks = f"Group payment via Fast Entry"

    default_bank = frappe.db.get_value("Company", company, "default_bank_account") or _first_bank_account(company)
    if not default_bank:
        frappe.throw(_("No Bank Account found for company {0}").format(company))

    if payment_type == "Pay":
        pe.paid_from = default_bank
        pe.paid_to = _party_account(company, party_type, party)
    else:
        pe.paid_from = _party_account(company, party_type, party)
        pe.paid_to = default_bank

    for r in rows:
        pe.append("references", {
            "reference_doctype": ref_doctype,
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


def _party_account(company, party_type, party):
    """Get party-specific account or company default."""
    if party_type == "Supplier":
        acc = frappe.db.get_value(
            "Party Account",
            {"parenttype": "Supplier", "parent": party, "company": company},
            "account",
        )
        if acc:
            return acc
        return frappe.db.get_value("Company", company, "default_payable_account") or _first_account(company, "Payable")
    else:
        acc = frappe.db.get_value(
            "Party Account",
            {"parenttype": "Customer", "parent": party, "company": company},
            "account",
        )
        if acc:
            return acc
        return frappe.db.get_value("Company", company, "default_receivable_account") or _first_account(company, "Receivable")


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
