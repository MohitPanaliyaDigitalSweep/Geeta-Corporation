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
    """All unpaid invoices of a SINGLE party, oldest first.

    Deliberately NOT expanded across the party's group. The grouped view has its
    own endpoint (get_pending_party_group_invoices); a caller who wants the
    group-wide view must pick the group in the dropdown.

    Response mirrors _pending_grouped_invoices so the payment pages can render
    either kind with the same code:
        {parties, invoices, by_party, total_outstanding, group}
    """
    if party_type not in ("Customer", "Supplier"):
        return {"parties": [], "invoices": [], "by_party": {}, "total_outstanding": 0,
                "group": "", "advance_balance": 0, "carry_applied_total": 0}
    if not company or not party:
        return {"parties": [], "invoices": [], "by_party": {}, "total_outstanding": 0,
                "group": "", "advance_balance": 0, "carry_applied_total": 0}

    doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
    party_field = "customer" if party_type == "Customer" else "supplier"
    party_name = _display_name(party_type, party)

    invoices = frappe.get_all(
        doctype,
        filters={"company": company, party_field: party, "docstatus": 1, "outstanding_amount": [">", 0.01]},
        fields=["name", party_field, "posting_date", "due_date", "grand_total", "outstanding_amount"],
        order_by="posting_date asc, name asc",
    )
    for inv in invoices:
        inv["party_name"] = party_name

    total = sum(flt(i.outstanding_amount) for i in invoices)
    carry_summary = _attach_carry(company, party_type, invoices)
    carry_total = sum(flt(v) for p in carry_summary.values() for v in p["per_invoice"].values())
    advance_balance = flt(carry_summary.get(party, {}).get("balance", 0.0)) if invoices else 0.0
    by_party = {}
    if invoices:
        by_party[party] = {
            "party": party,
            "party_name": party_name,
            "party_type": party_type,
            "invoices": invoices,
            "total": total,
            "advance_balance": advance_balance,
            "carry_applied_total": round(carry_total, 2),
        }

    return {
        "parties": [_party_ref(party_type, party)] if invoices else [],
        "invoices": invoices,
        "by_party": by_party,
        "total_outstanding": total,
        "group": "",
        "advance_balance": advance_balance,
        "carry_applied_total": round(carry_total, 2),
    }


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
    carry_summary = _attach_carry(company, party_type, invoices)
    carry_total = sum(flt(v) for p in carry_summary.values() for v in p["per_invoice"].values())

    # Per-member subtotals, so group mode can show what each member owes before
    # the run happens rather than only the group total.
    by_party = {}
    for inv in invoices:
        key = inv.get(party_field)
        entry = by_party.setdefault(key, {"party": key, "party_name": inv["party_name"],
                                          "party_type": party_type, "invoices": [], "total": 0.0,
                                          "advance_balance": 0.0, "carry_applied_total": 0.0})
        entry["invoices"].append(inv)
        entry["total"] += flt(inv.outstanding_amount)
    for key, entry in by_party.items():
        plan = carry_summary.get(key) or {}
        entry["advance_balance"] = round(flt(plan.get("balance", 0.0)), 2)
        entry["carry_applied_total"] = round(sum(flt(v) for v in (plan.get("per_invoice") or {}).values()), 2)

    return {
        "parties": parties,
        "party_names": names,
        "invoices": invoices,
        "by_party": by_party,
        "total_outstanding": total,
        "group": group_name,
        "carry_applied_total": round(carry_total, 2),
    }


@frappe.whitelist()
def create_bulk_supplier_payment(data):
    """Create Payment Entries for selected Purchase Invoices (full or partial per
    invoice, via checkboxes). One Payment Entry per supplier, so grouped
    suppliers (fe_group) are paid in a single action.

    data = {
        company, posting_date, mode_of_payment, reference_no, reference_date,
        items: [{name (Purchase Invoice), supplier, pay_amount, tds, advance}]
    }

    Per-row TDS/advance: each row may carry its own tds and advance box
    values; an amount above the invoice's outstanding becomes row advance
    (auto-excess). The party's oldest unallocated advance is auto-applied
    first (carry-forward, reconciliation-style).
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
        # No pay > outstanding guard here: an amount above the invoice's
        # outstanding is booked as per-row advance (auto-excess) by the maker.
        validated.append({
            "name": it.get("name"),
            "supplier": pi.supplier,
            "pay_amount": pay_amount,
            "tds": flt(it.get("tds")),
            "advance": flt(it.get("advance")),
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
            "allocated": getattr(pe, "fe_total_allocated", 0.0),
            "tds": getattr(pe, "fe_total_tds", 0.0),
            "advance": getattr(pe, "fe_total_advance", 0.0),
            "carry_applied": getattr(pe, "fe_carry_applied", 0.0),
        })

    return {
        "payments": payments,
        "count": len(payments),
        "total": sum(flt(p["amount"]) for p in payments),
    }


def _make_supplier_payment(company, supplier, rows, data):
    # Carry-forward first: the supplier's oldest unallocated advance is
    # reconciled against the selected invoices, inside this transaction.
    _apply_advance_to_rows(company, "Supplier", supplier, rows)
    carry_total = sum(flt(r.get("carry_applied") or 0) for r in rows)

    # Per-invoice books. O' is the invoice's outstanding after carry-forward;
    # the reference allocates min(pay, O') and any excess becomes row advance
    # (auto-excess), so a To Pay above outstanding never overpays the bill.
    allocations = []
    total_alloc = 0.0
    total_tds = 0.0
    total_advance = 0.0
    for r in rows:
        eff = max(flt(r["outstanding_amount"]) - flt(r.get("carry_applied") or 0), 0.0)
        alloc = min(flt(r["pay_amount"]), eff)
        excess = flt(r["pay_amount"]) - alloc
        tds = flt(r.get("tds"))
        if tds > eff + 0.01:
            frappe.throw(
                _("TDS (Rs. {0}) for {1} cannot exceed its outstanding (Rs. {2}). Reduce the TDS amount.").format(
                    tds, r["name"], eff
                )
            )
        adv = flt(r.get("advance")) + max(excess, 0.0)
        allocations.append({
            "name": r["name"],
            "outstanding": eff,
            "allocated": alloc,
            "tds": tds,
            "advance": adv,
            "grand_total": flt(r["grand_total"]),
        })
        total_alloc += alloc
        total_tds += tds
        total_advance += adv

    # Verified construction (supplier / Pay), generalised to per-bill sums:
    #   paid_amount = total_allocated + total_advance - total_tds
    #   deductions = one row per bill with TDS, posted as NEGATIVE so the
    #   general ledger credits TDS Payable (tax withheld and owed to the
    #   government) instead of debiting it. ERPNext flips negative debit
    #   legs to credits (toggle_debit_credit_if_negative), so the books read:
    #   Dr Payable (alloc + advance) = Cr Bank (net paid) + Cr TDS Payable.
    # References allocate the residual after carry-forward, so each invoice
    # outstanding goes to zero across the old advance PEs + this PE; the
    # advance becomes the unallocated (on-account) remainder.
    paid_amount = total_alloc + total_advance - total_tds
    if paid_amount <= 0:
        frappe.throw(_("TDS ({0}) exceeds payable + advance ({1}). Reduce the TDS amount.").format(total_tds, total_alloc + total_advance))

    pe = frappe.new_doc("Payment Entry")
    pe.company = company
    pe.payment_type = "Pay"
    pe.party_type = "Supplier"
    pe.party = supplier
    pe.posting_date = getdate(data.get("posting_date")) or frappe.utils.today()
    pe.mode_of_payment = data.get("mode_of_payment") or _default_mode_of_payment(company)
    pe.paid_amount = paid_amount
    pe.received_amount = paid_amount
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

    for a in allocations:
        if a["allocated"] <= 0.01:
            continue
        pe.append("references", {
            "reference_doctype": "Purchase Invoice",
            "reference_name": a["name"],
            "total_amount": a["grand_total"],
            "outstanding_amount": a["outstanding"],
            "allocated_amount": a["allocated"],
        })

    if total_tds > 0:
        # Throws naming the exact TDS Payable account to create when missing.
        account = _tds_account(company, "Supplier")
        cost_center = _payment_cost_center(company)
        for a in allocations:
            if a["tds"] > 0:
                pe.append("deductions", {
                    "account": account,
                    # Negative: books Cr TDS Payable (withheld tax owed),
                    # so the bank pays the invoice net of TDS.
                    "amount": -a["tds"],
                    "cost_center": cost_center,
                })

    pe.flags.ignore_permissions = True
    pe.flags.ignore_links = True
    pe.save(ignore_permissions=True)
    pe.submit()
    pe.fe_total_allocated = total_alloc
    pe.fe_total_tds = total_tds
    pe.fe_total_advance = total_advance
    pe.fe_carry_applied = carry_total
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


def _tds_account(company, party_type):
    """Direction-correct TDS account, strictly enforced (no silent fallback).

    Customer/Receive -> TDS Receivable - <abbr>; Supplier/Pay ->
    TDS Payable - <abbr>. Throws naming the exact account to create when it
    is missing, so TDS can never post to the wrong-direction account.
    """
    abbr = frappe.db.get_value("Company", company, "abbr")
    expected = (f"TDS Receivable - {abbr}" if party_type == "Customer"
                else f"TDS Payable - {abbr}")
    if frappe.db.exists("Account", expected):
        return expected
    frappe.throw(
        _("TDS entered but '{0}' does not exist for company {1}. Create the '{0}' account first.").format(
            expected, company
        )
    )


def _payment_cost_center(company):
    """Company default cost center, else the first non-group one."""
    cc = frappe.db.get_value("Company", company, "cost_center")
    if cc:
        return cc
    return frappe.db.get_value(
        "Cost Center", {"is_group": 0, "company": company}, "name", order_by="name asc"
    )


def _party_advance_balance(company, party_type, party):
    """Unallocated advance held in this party's submitted Payment Entries.

    A Payment Entry is an advance holder when it still has unallocated_amount
    > 0.01. Only the matching direction counts (Receive for Customer, Pay for
    Supplier). Oldest first (posting_date, creation) so carry-forward consumes
    the oldest advance before newer ones.
    """
    payment_type = "Receive" if party_type == "Customer" else "Pay"
    entries = frappe.get_all(
        "Payment Entry",
        filters={
            "company": company,
            "party_type": party_type,
            "party": party,
            "payment_type": payment_type,
            "docstatus": 1,
            "unallocated_amount": [">", 0.01],
        },
        fields=["name", "posting_date", "creation", "unallocated_amount"],
        order_by="posting_date asc, creation asc",
    )
    return {"total": sum(flt(e.unallocated_amount) for e in entries), "entries": entries}


def _carry_plan(company, party_type, party, invoices):
    """How the party's unallocated advance would auto-apply to its pending
    invoices, oldest invoice first (reconciliation-style carry-forward).

    `invoices` must be the party's FULL pending list, oldest first, each with
    name / grand_total / outstanding_amount. Pure computation - no DB writes.
    Returns {balance, applied_total, remaining_balance, per_invoice, entries}
    where entries are frappe._dict rows ready for reconcile_against_document.
    """
    bal = _party_advance_balance(company, party_type, party)
    plan = {
        "balance": flt(bal["total"]),
        "applied_total": 0.0,
        "remaining_balance": flt(bal["total"]),
        "per_invoice": {},
        "entries": [],
    }
    if not bal["entries"] or not invoices:
        return plan

    doctype = "Sales Invoice" if party_type == "Customer" else "Purchase Invoice"
    if party_type == "Customer":
        account = frappe.db.get_value("Company", company, "default_receivable_account") or _first_account(company, "Receivable")
    else:
        account = _supplier_payable_account(company, party)

    remaining_by_inv = {}
    for inv in invoices:
        remaining_by_inv[inv["name"]] = flt(inv.get("outstanding_amount"))

    for pe in bal["entries"]:
        rem = flt(pe.unallocated_amount)
        if rem <= 0.01:
            continue
        for inv in invoices:
            if rem <= 0.01:
                break
            avail = remaining_by_inv.get(inv["name"], 0.0)
            if avail <= 0.01:
                continue
            take = min(rem, avail)
            plan["entries"].append(frappe._dict({
                "voucher_type": "Payment Entry",
                "voucher_no": pe.name,
                "against_voucher_type": doctype,
                "against_voucher": inv["name"],
                "account": account,
                "party_type": party_type,
                "party": party,
                "allocated_amount": take,
                # Both checks in reconcile_against_document run pre-save against
                # DB state, so every entry carries the PE's full unallocated.
                "unreconciled_amount": flt(pe.unallocated_amount),
                "unadjusted_amount": flt(pe.unallocated_amount),
                "grand_total": flt(inv.get("grand_total")),
                "outstanding_amount": avail,
                "exchange_rate": 1,
            }))
            remaining_by_inv[inv["name"]] = avail - take
            plan["per_invoice"][inv["name"]] = plan["per_invoice"].get(inv["name"], 0.0) + take
            plan["applied_total"] += take
            rem -= take

    plan["remaining_balance"] = flt(plan["balance"] - plan["applied_total"])
    return plan


def _attach_carry(company, party_type, invoices):
    """Attach advance/carry fields to each invoice dict in place.

    Groups `invoices` per party and runs the same oldest-first plan the makers
    use, so the UI's effective outstanding always agrees with the server:
      inv.advance_balance        - party's total unallocated advance
      inv.carry_applied          - advance auto-applied to THIS invoice
      inv.effective_outstanding  - outstanding_amount - carry_applied
    Returns {party: plan}.
    """
    key_field = "customer" if party_type == "Customer" else "supplier"
    by_party = {}
    order = []
    for inv in invoices:
        key = inv.get(key_field)
        if key not in by_party:
            by_party[key] = []
            order.append(key)
        by_party[key].append(inv)

    summary = {}
    for key in order:
        plan = _carry_plan(company, party_type, key, by_party[key])
        summary[key] = plan
        for inv in by_party[key]:
            carry = round(flt(plan["per_invoice"].get(inv["name"], 0.0)), 2)
            inv["advance_balance"] = round(flt(plan["balance"]), 2)
            inv["carry_applied"] = carry
            inv["effective_outstanding"] = round(max(flt(inv.get("outstanding_amount")) - carry, 0.0), 2)
    return summary


def _reconcile_entries(entries):
    """Append the given carry entries to their old advance Payment Entries."""
    if not entries:
        return
    from erpnext.accounts.utils import reconcile_against_document

    reconcile_against_document(entries)


def _apply_advance_to_rows(company, party_type, party, rows):
    """Auto-apply the party's oldest unallocated advance to the SELECTED rows.

    The plan is computed against the party's FULL pending list (so the amounts
    match what the UI showed), but only entries for the selected rows are
    applied. Runs inside the current transaction, atomic with the new PE.
    Stamps each row's `carry_applied`; returns the full plan.
    """
    selected = {r["name"] for r in rows}
    pending = get_pending_invoices(company, party_type, party).get("invoices") or []
    plan = _carry_plan(company, party_type, party, pending)
    entries = [e for e in plan["entries"] if e["against_voucher"] in selected]
    _reconcile_entries(entries)
    carried = {}
    for e in entries:
        carried[e["against_voucher"]] = carried.get(e["against_voucher"], 0.0) + flt(e["allocated_amount"])
    for r in rows:
        r["carry_applied"] = round(flt(carried.get(r["name"], 0.0)), 2)
    return plan


def _distribute_group_tds_advance(data, prepared):
    """Split a single TDS / Advance figure across the group's member PEs.

    Only members that pay invoices receive a share; a purely on-account member
    (no invoice rows) keeps just its own advance, so the entered totals are not
    double counted. Shares are proportional to each member's invoice allocation,
    with the rounding remainder landed on the last paying member so the sum of
    per-entry tds/advance equals exactly what the user entered.
    """
    tds_total = flt(data.get("tds"))
    advance_total = flt(data.get("advance"))
    share_base = sum(flt(p["pay_amount"]) for p in prepared if p["rows"])
    if share_base <= 0 or not (tds_total or advance_total):
        return {p["party"]: {"tds": 0.0, "advance": 0.0} for p in prepared}

    paying = [p for p in prepared if p["rows"]]
    out = {}
    tds_left = tds_total
    advance_left = advance_total
    for idx, p in enumerate(paying):
        is_last = idx == len(paying) - 1
        if is_last:
            out[p["party"]] = {"tds": round(tds_left, 2), "advance": round(advance_left, 2)}
            continue
        share = flt(p["pay_amount"]) / share_base
        member_tds = round(tds_total * share, 2)
        member_advance = round(advance_total * share, 2)
        out[p["party"]] = {"tds": member_tds, "advance": member_advance}
        tds_left = round(tds_left - member_tds, 2)
        advance_left = round(advance_left - member_advance, 2)

    for p in prepared:
        out.setdefault(p["party"], {"tds": 0.0, "advance": 0.0})
    return out


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
        items: [{name (Sales Invoice), customer, pay_amount, tds, advance}]
    }

    Per-row TDS/advance: each row may carry its own tds and advance box
    values; an amount above the invoice's outstanding becomes row advance
    (auto-excess). The party's oldest unallocated advance is auto-applied
    first (carry-forward, reconciliation-style).
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
        # No pay > outstanding guard here: an amount above the invoice's
        # outstanding is booked as per-row advance (auto-excess) by the maker.
        validated.append({
            "name": it.get("name"),
            "customer": si.customer,
            "pay_amount": pay_amount,
            "tds": flt(it.get("tds")),
            "advance": flt(it.get("advance")),
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
            "allocated": getattr(pe, "fe_total_allocated", 0.0),
            "tds": getattr(pe, "fe_total_tds", 0.0),
            "advance": getattr(pe, "fe_total_advance", 0.0),
            "carry_applied": getattr(pe, "fe_carry_applied", 0.0),
        })

    return {
        "payments": payments,
        "count": len(payments),
        "total": sum(flt(p["amount"]) for p in payments),
    }


def _make_customer_payment(company, customer, rows, data):
    # Carry-forward first: the customer's oldest unallocated advance is
    # reconciled against the selected invoices, inside this transaction.
    _apply_advance_to_rows(company, "Customer", customer, rows)
    carry_total = sum(flt(r.get("carry_applied") or 0) for r in rows)

    # Per-invoice books. O' is the invoice's outstanding after carry-forward;
    # the reference allocates min(pay, O') and any excess becomes row advance
    # (auto-excess), so a To Receive above outstanding never overpays the bill.
    allocations = []
    total_alloc = 0.0
    total_tds = 0.0
    total_advance = 0.0
    for r in rows:
        eff = max(flt(r["outstanding_amount"]) - flt(r.get("carry_applied") or 0), 0.0)
        alloc = min(flt(r["pay_amount"]), eff)
        excess = flt(r["pay_amount"]) - alloc
        tds = flt(r.get("tds"))
        if tds > eff + 0.01:
            frappe.throw(
                _("TDS (Rs. {0}) for {1} cannot exceed its outstanding (Rs. {2}). Reduce the TDS amount.").format(
                    tds, r["name"], eff
                )
            )
        adv = flt(r.get("advance")) + max(excess, 0.0)
        allocations.append({
            "name": r["name"],
            "outstanding": eff,
            "allocated": alloc,
            "tds": tds,
            "advance": adv,
            "grand_total": flt(r["grand_total"]),
        })
        total_alloc += alloc
        total_tds += tds
        total_advance += adv

    # Verified construction (customer / Receive), generalised to per-bill sums:
    #   paid_amount = total_allocated + total_advance - total_tds
    #   deductions = one row per bill with TDS
    paid_amount = total_alloc + total_advance - total_tds
    if paid_amount <= 0:
        frappe.throw(_("TDS ({0}) exceeds receivable + advance ({1}). Reduce the TDS amount.").format(total_tds, total_alloc + total_advance))

    pe = frappe.new_doc("Payment Entry")
    pe.company = company
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = customer
    pe.posting_date = getdate(data.get("posting_date")) or frappe.utils.today()
    pe.mode_of_payment = data.get("mode_of_payment") or _default_mode_of_payment(company)
    pe.paid_amount = paid_amount
    pe.received_amount = paid_amount
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

    for a in allocations:
        if a["allocated"] <= 0.01:
            continue
        pe.append("references", {
            "reference_doctype": "Sales Invoice",
            "reference_name": a["name"],
            "total_amount": a["grand_total"],
            "outstanding_amount": a["outstanding"],
            "allocated_amount": a["allocated"],
        })

    if total_tds > 0:
        # Throws naming the exact TDS Receivable account to create when missing.
        account = _tds_account(company, "Customer")
        cost_center = _payment_cost_center(company)
        for a in allocations:
            if a["tds"] > 0:
                pe.append("deductions", {
                    "account": account,
                    "amount": a["tds"],
                    "cost_center": cost_center,
                })

    pe.flags.ignore_permissions = True
    pe.flags.ignore_links = True
    pe.save(ignore_permissions=True)
    pe.submit()
    pe.fe_total_allocated = total_alloc
    pe.fe_total_tds = total_tds
    pe.fe_total_advance = total_advance
    pe.fe_carry_applied = carry_total
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
        if g.get("group_type") and g.get("group_type") != "Both" and g.get("group_type") != party_type:
            continue
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
        items: [{party, pay_amount, invoices: [{name, pay_amount, tds, advance}]}]
    }

    Per-row TDS/advance ride on the invoice rows (see the bulk makers); the
    whole-run data.tds/data.advance split survives only as a fallback for
    stale cached pages that send no per-row figures.
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
            # No pay > outstanding guard: an amount above outstanding is
            # booked as per-row advance (auto-excess) by the maker.
            rows.append({
                "name": ref.get("name"),
                "pay_amount": pay_amount,
                "tds": flt(ref.get("tds")),
                "advance": flt(ref.get("advance")),
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

    # Per-row TDS/advance ride on the invoice rows now. Fall back to the old
    # whole-run split only for callers that still send data.tds/data.advance
    # with no per-row figures (stale cached page); the share lands on the
    # member's first row, which is bookkeeping-equivalent for the PE totals.
    rowwise = any(flt(r.get("tds")) or flt(r.get("advance")) for p in prepared for r in p["rows"])
    if not rowwise and (flt(data.get("tds")) or flt(data.get("advance"))):
        tds_advance = _distribute_group_tds_advance(data, prepared)
        for p in prepared:
            if p["rows"]:
                p["rows"][0]["tds"] = flt(p["rows"][0].get("tds")) + tds_advance[p["party"]]["tds"]
                p["rows"][0]["advance"] = flt(p["rows"][0].get("advance")) + tds_advance[p["party"]]["advance"]

    payments = []
    for p in prepared:
        member_data = dict(shared)
        if p["rows"]:
            maker = _make_customer_payment if party_type == "Customer" else _make_supplier_payment
            pe = maker(company, p["party"], p["rows"], member_data)
        else:
            pe = _make_advance_payment(company, party_type, p["party"], p["pay_amount"], member_data)
        payments.append({
            "party": p["party"],
            "party_name": p["party_name"],
            "payment_entry": pe.name,
            "paid_amount": flt(pe.paid_amount),
            "invoice_count": p["invoice_count"],
            "outstanding_before": p["outstanding_before"],
            "allocated": getattr(pe, "fe_total_allocated", 0.0),
            "tds": getattr(pe, "fe_total_tds", 0.0),
            "advance": getattr(pe, "fe_total_advance", 0.0),
            "carry_applied": getattr(pe, "fe_carry_applied", 0.0),
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
