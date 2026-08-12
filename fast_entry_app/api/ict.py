import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def create_inter_company_transfer(data):
    """Create an Inter Company Transfer document (Draft)."""
    if isinstance(data, str):
        import json
        data = json.loads(data)

    errors = validate_ict(data)
    if errors:
        frappe.throw(errors)

    doc = frappe.new_doc("Inter Company Transfer")
    doc.company = data["company"]
    doc.to_company = data["to_company"]
    doc.posting_date = data.get("posting_date") or frappe.utils.today()
    doc.remarks = data.get("remarks", "")
    if data.get("sales_tax_template"):
        doc.sales_tax_template = data["sales_tax_template"]
    if data.get("purchase_tax_template"):
        doc.purchase_tax_template = data["purchase_tax_template"]

    for item_data in data.get("items", []):
        item_code = str(item_data.get("item_code", "")).strip()
        if not item_code:
            continue
        qty = flt(item_data.get("qty", 0))
        rate = flt(item_data.get("rate", 0))
        box = flt(item_data.get("box", 0))
        pcs = flt(item_data.get("pcs", 0))
        ltr = flt(item_data.get("ltr", 0))
        total_ltr = qty  # qty IS total litre
        doc.append("items", {
            "item_code": item_code,
            "qty": qty,
            "uom": item_data.get("uom", "Litre"),
            "rate": rate,
            "amount": pcs * rate if pcs else qty * rate,
            "source_warehouse": item_data.get("source_warehouse"),
            "target_warehouse": item_data.get("target_warehouse"),
            "fe_box": box,
            "fe_pcs": pcs,
            "fe_ltr": ltr,
            "fe_total_ltr": total_ltr,
        })

    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)

    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def submit_inter_company_transfer(name):
    """Submit ICT and create full document chain: SO→PO→DN→PR→SI→PI.
    After chain creation, propagate fe_box/fe_pcs/fe_ltr/fe_total_ltr to SI and PI items."""
    doc = frappe.get_doc("Inter Company Transfer", name)
    if doc.docstatus != 0:
        frappe.throw(_("Only Draft documents can be submitted"))

    # Collect fe_ values from ICT items before submit (by item_code)
    fe_data = {}
    for row in doc.items:
        if row.item_code and (row.get("fe_box") or row.get("fe_pcs") or row.get("fe_ltr") or row.get("fe_total_ltr")):
            fe_data[row.item_code] = {
                "fe_box": flt(row.get("fe_box", 0)),
                "fe_pcs": flt(row.get("fe_pcs", 0)),
                "fe_ltr": flt(row.get("fe_ltr", 0)),
                "fe_total_ltr": flt(row.get("fe_total_ltr", 0)),
            }

    doc.submit()

    # Propagate fe_ values to SI and PI items
    if fe_data:
        _propagate_fe_values(doc, fe_data)

    steps = get_progress_status(name)
    return {"name": doc.name, "status": doc.status, "steps": steps}


def _propagate_fe_values(ict_doc, fe_data):
    """Set fe_box/fe_pcs/fe_ltr/fe_total_ltr on SI and PI items from ICT data."""
    for doctype, field in [("Sales Invoice", "sales_invoice"), ("Purchase Invoice", "purchase_invoice")]:
        docname = ict_doc.get(field)
        if not docname:
            continue
        try:
            d = frappe.get_doc(doctype, docname)
            for item in d.items:
                if item.item_code in fe_data:
                    fd = fe_data[item.item_code]
                    item.db_set({
                        "fe_box": fd["fe_box"],
                        "fe_pcs": fd["fe_pcs"],
                        "fe_ltr": fd["fe_ltr"],
                        "fe_total_ltr": fd["fe_total_ltr"],
                    }, update_modified=False)
        except Exception as e:
            frappe.log_error(title=f"ICT propagate fe_ values: {doctype} {docname}", message=str(e))


@frappe.whitelist()
def cancel_inter_company_transfer(name):
    """Cancel ICT and all generated documents."""
    doc = frappe.get_doc("Inter Company Transfer", name)
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted documents can be cancelled"))
    doc.cancel()
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_progress_status(name):
    """Get progress of all generated documents in the chain."""
    doc = frappe.get_doc("Inter Company Transfer", name)
    steps = []
    for doctype, field, short, icon, color in [
        ("Sales Order", "sales_order", "SO", "fa fa-file-text-o", "#3b82f6"),
        ("Purchase Order", "purchase_order", "PO", "fa fa-shopping-cart", "#10b981"),
        ("Delivery Note", "delivery_note", "DN", "fa fa-truck", "#f59e0b"),
        ("Purchase Receipt", "purchase_receipt", "PR", "fa fa-truck", "#8b5cf6"),
        ("Sales Invoice", "sales_invoice", "SI", "fa fa-credit-card", "#ef4444"),
        ("Purchase Invoice", "purchase_invoice", "PI", "fa fa-file-text-o", "#06b6d4"),
    ]:
        docname = doc.get(field)
        if docname:
            try:
                d = frappe.get_doc(doctype, docname)
                steps.append({
                    "doctype": doctype, "name": docname, "short": short,
                    "icon": icon, "color": color,
                    "status": "Submitted" if d.docstatus == 1 else "Draft",
                    "grand_total": flt(d.grand_total),
                    "outstanding": flt(d.get("outstanding_amount", 0)),
                })
            except Exception:
                steps.append({"doctype": doctype, "name": docname, "short": short,
                              "icon": icon, "color": color, "status": "Error",
                              "grand_total": 0, "outstanding": 0})
        else:
            steps.append({"doctype": doctype, "name": None, "short": short,
                          "icon": icon, "color": color, "status": "Pending",
                          "grand_total": 0, "outstanding": 0})
    return steps


@frappe.whitelist()
def get_generated_documents(name):
    """Get details of all generated documents with status, amounts, company, and tax details."""
    doc = frappe.get_doc("Inter Company Transfer", name)
    docs = []
    for doctype, field, short, color in [
        ("Sales Order", "sales_order", "SO", "#3b82f6"),
        ("Purchase Order", "purchase_order", "PO", "#10b981"),
        ("Delivery Note", "delivery_note", "DN", "#f59e0b"),
        ("Purchase Receipt", "purchase_receipt", "PR", "#8b5cf6"),
        ("Sales Invoice", "sales_invoice", "SI", "#ef4444"),
        ("Purchase Invoice", "purchase_invoice", "PI", "#06b6d4"),
    ]:
        docname = doc.get(field)
        entry = {"doctype": doctype, "name": docname, "short": short, "color": color,
                 "status": "Pending", "grand_total": 0, "company": "", "posting_date": "",
                 "base_total": 0, "tax_amount": 0, "tax_rate": 0, "tax_account": "",
                 "net_total": 0, "outstanding": 0}
        if docname:
            try:
                d = frappe.get_doc(doctype, docname)
                entry["status"] = "Submitted" if d.docstatus == 1 else "Draft"
                entry["grand_total"] = flt(d.grand_total)
                entry["company"] = d.company
                entry["posting_date"] = str(d.get("posting_date", ""))
                entry["net_total"] = flt(d.get("net_total", 0))
                entry["outstanding"] = flt(d.get("outstanding_amount", 0))
                # Extract tax details
                if d.get("taxes"):
                    total_tax = 0
                    tax_rate = 0
                    tax_account = ""
                    for t in d.taxes:
                        tax_amount = flt(t.get("tax_amount", 0))
                        total_tax += tax_amount
                        if tax_amount > 0:
                            tax_rate = flt(t.get("rate", 0))
                            tax_account = t.get("account_head", "")
                    entry["tax_amount"] = total_tax
                    entry["tax_rate"] = tax_rate
                    entry["tax_account"] = tax_account
                entry["base_total"] = flt(d.get("base_grand_total", d.grand_total))
                # Extract fe_ values for SI/PI
                if doctype in ("Sales Invoice", "Purchase Invoice") and d.get("items"):
                    total_box = sum(flt(it.get("fe_box", 0)) for it in d.items)
                    total_pcs = sum(flt(it.get("fe_pcs", 0)) for it in d.items)
                    total_ltr = sum(flt(it.get("fe_total_ltr", 0)) for it in d.items)
                    entry["fe_box"] = total_box
                    entry["fe_pcs"] = total_pcs
                    entry["fe_total_ltr"] = total_ltr
            except Exception:
                entry["status"] = "Error"
        docs.append(entry)
    return docs


@frappe.whitelist()
def get_stock_breakdown(name):
    """Get stock qty across warehouses for each item in the transfer."""
    doc = frappe.get_doc("Inter Company Transfer", name)
    item_codes = [row.item_code for row in doc.items if row.item_code]
    if not item_codes:
        return {}

    result = {}
    for ic in item_codes:
        sle = frappe.db.sql("""
            SELECT warehouse, company, SUM(actual_qty) as qty, SUM(stock_value) as val
            FROM `tabStock Ledger Entry`
            WHERE item_code = %s AND company IN (%s, %s)
            GROUP BY warehouse, company
            HAVING SUM(actual_qty) != 0
            ORDER BY company, warehouse
        """, (ic, doc.company, doc.to_company), as_dict=True)
        result[ic] = sle
    return result


@frappe.whitelist()
def get_ict_details(name):
    """Get full ICT details including items, warehouses, document links, and outstanding amounts."""
    doc = frappe.get_doc("Inter Company Transfer", name)
    items = []
    for row in doc.items:
        items.append({
            "item_code": row.item_code,
            "item_name": row.item_name,
            "qty": flt(row.qty),
            "uom": row.uom,
            "rate": flt(row.rate),
            "amount": flt(row.amount),
            "source_warehouse": row.source_warehouse,
            "target_warehouse": row.target_warehouse,
            "batch_no": row.batch_no,
            "fe_box": flt(row.get("fe_box", 0)),
            "fe_pcs": flt(row.get("fe_pcs", 0)),
            "fe_ltr": flt(row.get("fe_ltr", 0)),
            "fe_total_ltr": flt(row.get("fe_total_ltr", 0)),
        })

    result = {
        "name": doc.name,
        "company": doc.company,
        "to_company": doc.to_company,
        "posting_date": str(doc.posting_date),
        "status": doc.status,
        "docstatus": doc.docstatus,
        "remarks": doc.remarks,
        "total_qty": flt(doc.total_qty),
        "grand_total": flt(doc.grand_total),
        "items": items,
        "sales_order": doc.sales_order,
        "purchase_order": doc.purchase_order,
        "delivery_note": doc.delivery_note,
        "purchase_receipt": doc.purchase_receipt,
        "sales_invoice": doc.sales_invoice,
        "purchase_invoice": doc.purchase_invoice,
    }

    # Add outstanding amounts for invoices
    if doc.sales_invoice:
        try:
            si = frappe.get_doc("Sales Invoice", doc.sales_invoice)
            result["si_grand_total"] = flt(si.grand_total)
            result["si_outstanding"] = flt(si.outstanding_amount)
        except Exception:
            result["si_grand_total"] = 0
            result["si_outstanding"] = 0

    if doc.purchase_invoice:
        try:
            pi = frappe.get_doc("Purchase Invoice", doc.purchase_invoice)
            result["pi_grand_total"] = flt(pi.grand_total)
            result["pi_outstanding"] = flt(pi.outstanding_amount)
        except Exception:
            result["pi_grand_total"] = 0
            result["pi_outstanding"] = 0

    return result


@frappe.whitelist()
def create_payment_entry_manual(name, doctype, docname, amount, mode_of_payment=None, posting_date=None, reference_no=None):
    """Create a Payment Entry with manual parameters for an ICT-generated document."""
    if doctype not in ("Sales Invoice", "Purchase Invoice"):
        frappe.throw(_("Payment can only be created for Sales Invoice or Purchase Invoice"))

    doc = frappe.get_doc(doctype, docname)
    if doc.docstatus != 1:
        frappe.throw(_("Document must be submitted to create payment"))
    if flt(doc.outstanding_amount) <= 0:
        frappe.throw(_("No outstanding amount for {0}").format(docname))

    pay_amount = flt(amount)
    if pay_amount <= 0:
        frappe.throw(_("Payment amount must be greater than 0"))
    if pay_amount > flt(doc.outstanding_amount):
        frappe.throw(_("Payment amount {0} exceeds outstanding {1}").format(pay_amount, flt(doc.outstanding_amount)))

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive" if doctype == "Sales Invoice" else "Pay"
    pe.company = doc.company
    pe.posting_date = posting_date or frappe.utils.today()

    if doctype == "Sales Invoice":
        pe.party_type = "Customer"
        pe.party = doc.customer
        pe.paid_to = frappe.db.get_value("Company", doc.company, "default_receivable_account")
    else:
        pe.party_type = "Supplier"
        pe.party = doc.supplier
        pe.paid_from = frappe.db.get_value("Company", doc.company, "default_payable_account")

    pe.paid_amount = pay_amount
    pe.received_amount = pay_amount
    pe.reference_doctype = doctype
    pe.reference_name = docname
    pe.remarks = f"Payment for {doctype} {docname} (ICT: {name})"

    if mode_of_payment:
        pe.mode_of_payment = mode_of_payment
    if reference_no:
        pe.reference_no = reference_no

    pe.flags.ignore_permissions = True
    pe.insert(ignore_permissions=True)
    pe.submit()

    return {"name": pe.name, "status": "Submitted", "amount": pay_amount}


@frappe.whitelist()
def create_payment_entry_for_ict(name, doctype, docname, amount=None):
    """Legacy: Create a Payment Entry for an ICT-generated document (SI or PI)."""
    return create_payment_entry_manual(name, doctype, docname, amount or 0)


def validate_ict(data):
    """Validate inter company transfer data."""
    errors = []
    if not data.get("company"):
        errors.append("Source Company is required")
    if not data.get("to_company"):
        errors.append("Target Company is required")
    if data.get("company") and data.get("to_company") and data["company"] == data["to_company"]:
        errors.append("Source and Target companies cannot be the same")
    if not data.get("posting_date"):
        errors.append("Posting Date is required")

    items = data.get("items", [])
    valid_items = [i for i in items if i.get("item_code") and flt(i.get("qty", 0)) > 0]
    if not valid_items:
        errors.append("At least one item with Qty > 0 is required")

    for item in valid_items:
        if flt(item.get("rate", 0)) <= 0:
            errors.append(f"Row {item.get('idx', '?')}: Rate must be greater than 0")
        if not item.get("source_warehouse"):
            errors.append(f"Row {item.get('idx', '?')}: Source Warehouse is required")
        if not item.get("target_warehouse"):
            errors.append(f"Row {item.get('idx', '?')}: Target Warehouse is required")
        # Validate warehouse belongs to correct company
        src_wh_company = frappe.db.get_value("Warehouse", item.get("source_warehouse"), "company")
        if src_wh_company and src_wh_company != data["company"]:
            errors.append(f"Row {item.get('idx', '?')}: Source Warehouse belongs to {src_wh_company}, not {data['company']}")
        tgt_wh_company = frappe.db.get_value("Warehouse", item.get("target_warehouse"), "company")
        if tgt_wh_company and tgt_wh_company != data["to_company"]:
            errors.append(f"Row {item.get('idx', '?')}: Target Warehouse belongs to {tgt_wh_company}, not {data['to_company']}")

    return errors
