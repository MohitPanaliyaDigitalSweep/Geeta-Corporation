import frappe
from frappe import _
from frappe.utils import flt

# Resolvers shared with the sales/purchase entry APIs so that "Auto (Company
# Default)" means the same thing on every entry screen. Imported lazily inside
# the two functions below -- api.sales/api.purchase import api.item, and this
# module is imported from elsewhere, so keep the module level clean.
def _default_sales_template(company, gst_type):
    if not company:
        return ""
    try:
        from fast_entry_app.api.sales import _get_sales_tax_template
        return _get_sales_tax_template(company, gst_type) or ""
    except Exception:
        return ""


def _default_purchase_template(company, gst_type):
    if not company:
        return ""
    try:
        from fast_entry_app.api.purchase import _get_tax_template
        return _get_tax_template(company, gst_type) or ""
    except Exception:
        return ""


@frappe.whitelist()
def create_inter_company_transfer(data):
    """Create an Inter Company Transfer document (Draft)."""
    if isinstance(data, str):
        import json
        data = json.loads(data)

    errors = validate_ict(data)
    if errors:
        frappe.throw("<br>".join(errors))

    doc = frappe.new_doc("Inter Company Transfer")
    doc.company = data["company"]
    doc.to_company = data["to_company"]
    doc.posting_date = data.get("posting_date") or frappe.utils.today()
    doc.remarks = data.get("remarks", "")

    # "Auto (Company Default)" arrives as an empty string. Resolve it here so
    # the six generated documents (SO/PO/DN/PR/SI/PI) actually get tax rows --
    # their guards only fire when these fields are non-empty, and ERPNext's own
    # set_taxes() fallback cannot help (no template is flagged is_default and
    # Accounts Settings.add_taxes_from_taxes_and_charges_template is off).
    # Sales docs are on the source company, purchase docs on the target.
    gst_type = (data.get("gst_type") or "intra").lower()
    sales_template = data.get("sales_tax_template") or ""
    purchase_template = data.get("purchase_tax_template") or ""
    if not sales_template:
        sales_template = _default_sales_template(data["company"], gst_type)
    if not purchase_template:
        purchase_template = _default_purchase_template(data["to_company"], gst_type)

    doc.sales_tax_template = sales_template
    doc.purchase_tax_template = purchase_template

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

    doc.submit()

    steps = get_progress_status(name)
    return {"name": doc.name, "status": doc.status, "steps": steps}


@frappe.whitelist()
def cancel_inter_company_transfer(name):
    """Cancel ICT and all generated documents."""
    doc = frappe.get_doc("Inter Company Transfer", name)
    if doc.docstatus != 1:
        frappe.throw(_("Only submitted documents can be cancelled"))
    doc.cancel()
    return {"name": doc.name, "status": doc.status}


def _get_docname_by_type(doc, doctype):
    """Return document_name from the generated_documents child table for a doctype."""
    for row in doc.generated_documents:
        if row.document_type == doctype and row.document_name:
            return row.document_name
    return None


def _generated_chain():
    return [
        ("Sales Order", "SO", "fa fa-file-text-o", "#3b82f6"),
        ("Purchase Order", "PO", "fa fa-shopping-cart", "#10b981"),
        ("Delivery Note", "DN", "fa fa-truck", "#f59e0b"),
        ("Purchase Receipt", "PR", "fa fa-truck", "#8b5cf6"),
        ("Sales Invoice", "SI", "fa fa-credit-card", "#ef4444"),
        ("Purchase Invoice", "PI", "fa fa-file-text-o", "#06b6d4"),
    ]


@frappe.whitelist()
def get_progress_status(name):
    """Get progress of all generated documents in the chain."""
    doc = frappe.get_doc("Inter Company Transfer", name)
    steps = []
    for doctype, short, icon, color in _generated_chain():
        docname = _get_docname_by_type(doc, doctype)
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
    for doctype, short, color in [(d[0], d[1], d[3]) for d in _generated_chain()]:
        docname = _get_docname_by_type(doc, doctype)
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
                if d.get("items"):
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
        "sales_order": _get_docname_by_type(doc, "Sales Order"),
        "purchase_order": _get_docname_by_type(doc, "Purchase Order"),
        "delivery_note": _get_docname_by_type(doc, "Delivery Note"),
        "purchase_receipt": _get_docname_by_type(doc, "Purchase Receipt"),
        "sales_invoice": _get_docname_by_type(doc, "Sales Invoice"),
        "purchase_invoice": _get_docname_by_type(doc, "Purchase Invoice"),
    }

    if result["sales_invoice"]:
        try:
            si = frappe.get_doc("Sales Invoice", result["sales_invoice"])
            result["si_grand_total"] = flt(si.grand_total)
            result["si_outstanding"] = flt(si.outstanding_amount)
        except Exception:
            result["si_grand_total"] = 0
            result["si_outstanding"] = 0

    if result["purchase_invoice"]:
        try:
            pi = frappe.get_doc("Purchase Invoice", result["purchase_invoice"])
            result["pi_grand_total"] = flt(pi.grand_total)
            result["pi_outstanding"] = flt(pi.outstanding_amount)
        except Exception:
            result["pi_grand_total"] = 0
            result["pi_outstanding"] = 0

    return result


@frappe.whitelist()
def create_payment_entries_for_ict(ict_name, posting_date=None):
    """Create Payment Entries for the ICT's Sales Invoice (Receive) and Purchase Invoice (Pay).

    This is a separate manual step — payment entries are never auto-created on ICT submit."""
    if not ict_name:
        frappe.throw(_("ICT name is required"))

    ict = frappe.get_doc("Inter Company Transfer", ict_name)
    if ict.docstatus != 1:
        frappe.throw(_("ICT must be submitted"))

    if ict.status != "Transfer Created":
        frappe.throw(_("Documents must be created before creating payment entries"))

    si_name = _get_docname_by_type(ict, "Sales Invoice")
    pi_name = _get_docname_by_type(ict, "Purchase Invoice")

    if not si_name or not pi_name:
        frappe.throw(_("Sales Invoice / Purchase Invoice not found. Create documents first."))

    posting_date = posting_date or frappe.utils.today()
    pi_outstanding = frappe.db.get_value("Purchase Invoice", pi_name, "outstanding_amount") or 0
    si_outstanding = frappe.db.get_value("Sales Invoice", si_name, "outstanding_amount") or 0

    created = []

    if flt(pi_outstanding) > 0:
        pe = _make_ict_payment_entry(
            ict=ict,
            company=ict.to_company,
            party_type="Supplier",
            party=ict.get_internal_supplier(ict.company),
            payment_type="Pay",
            reference_doctype="Purchase Invoice",
            reference_name=pi_name,
            amount=pi_outstanding,
            posting_date=posting_date,
        )
        created.append(pe.name)

    if flt(si_outstanding) > 0:
        pe = _make_ict_payment_entry(
            ict=ict,
            company=ict.company,
            party_type="Customer",
            party=ict.get_internal_customer(ict.to_company),
            payment_type="Receive",
            reference_doctype="Sales Invoice",
            reference_name=si_name,
            amount=si_outstanding,
            posting_date=posting_date,
        )
        created.append(pe.name)

    if not created:
        frappe.msgprint(_("No outstanding amount found. Payment entries already created."))
        return {"created": []}

    ict.save(ignore_permissions=True)
    return {"created": created}


def _make_ict_payment_entry(ict, company, party_type, party, payment_type, reference_doctype, reference_name, amount, posting_date):
    pe = frappe.new_doc("Payment Entry")
    pe.company = company
    pe.payment_type = payment_type
    pe.party_type = party_type
    pe.party = party
    pe.posting_date = posting_date
    pe.mode_of_payment = frappe.db.get_value("Mode of Payment", {"type": "Bank"}, "name") or "Wire Transfer"
    pe.paid_amount = flt(amount)
    pe.received_amount = flt(amount)
    pe.source_exchange_rate = 1
    pe.target_exchange_rate = 1
    pe.reference_no = ict.name
    pe.reference_date = posting_date

    default_bank = frappe.db.get_value("Company", company, "default_bank_account")
    if not default_bank:
        frappe.throw(_("No default Bank Account set for company {0}").format(company))

    if payment_type == "Pay":
        default_payable = frappe.db.get_value("Company", company, "default_payable_account")
        pe.paid_from = default_bank
        pe.paid_to = default_payable
    else:
        default_receivable = frappe.db.get_value("Company", company, "default_receivable_account")
        pe.paid_from = default_receivable
        pe.paid_to = default_bank

    pe.append("references", {
        "reference_doctype": reference_doctype,
        "reference_name": reference_name,
        "total_amount": flt(amount),
        "outstanding_amount": flt(amount),
        "allocated_amount": flt(amount),
    })

    pe.flags.ignore_permissions = True
    pe.flags.ignore_links = True
    pe.save(ignore_permissions=True)
    pe.submit()

    ict.append("generated_documents", {
        "document_type": "Payment Entry",
        "document_name": pe.name,
        "company": pe.company,
        "status": "Submitted",
        "posting_date": posting_date,
        "grand_total": pe.paid_amount,
        "creation": frappe.utils.now(),
    })

    return pe


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
        src_wh_company = frappe.db.get_value("Warehouse", item.get("source_warehouse"), "company")
        if src_wh_company and src_wh_company != data["company"]:
            errors.append(f"Row {item.get('idx', '?')}: Source Warehouse belongs to {src_wh_company}, not {data['company']}")
        tgt_wh_company = frappe.db.get_value("Warehouse", item.get("target_warehouse"), "company")
        if tgt_wh_company and tgt_wh_company != data["to_company"]:
            errors.append(f"Row {item.get('idx', '?')}: Target Warehouse belongs to {tgt_wh_company}, not {data['to_company']}")

    return errors


@frappe.whitelist()
def get_tax_templates_with_details():
    """Return all Sales and Purchase tax templates with their tax rows."""
    result = {"sales": [], "purchase": []}

    for template in frappe.get_all("Sales Taxes and Charges Template", fields=["name", "company"]):
        taxes = frappe.get_all("Sales Taxes and Charges",
            filters={"parent": template.name},
            fields=["charge_type", "account_head", "rate", "description"])
        result["sales"].append({
            "name": template.name,
            "company": template.company,
            "taxes": taxes,
        })

    for template in frappe.get_all("Purchase Taxes and Charges Template", fields=["name", "company"]):
        taxes = frappe.get_all("Purchase Taxes and Charges",
            filters={"parent": template.name},
            fields=["charge_type", "account_head", "rate", "description"])
        result["purchase"].append({
            "name": template.name,
            "company": template.company,
            "taxes": taxes,
        })

    return result


@frappe.whitelist()
def calculate_tax_preview(items_json, template_name, tax_type="sales", company=None, gst_type="intra"):
    """Calculate tax amounts for given items and template.

    Args:
        items_json: JSON string of items [{item_code, pcs, rate, amount}, ...]
        template_name: Name of the tax template. Empty means "Auto (Company
            Default)" -- resolved against `company` when one is given.
        tax_type: "sales" or "purchase"
        company: Company to resolve an empty template_name against (sales leg
            passes the source company, purchase leg the target company).
        gst_type: "intra" or "inter", selects In-state / Out-state template.

    Returns:
        {net_total, tax_rows: [...], total_tax, grand_total, resolved_template}
        `resolved_template` is the template actually used, so the UI can say
        which one produced the rows when the operator left it on Auto.
    """
    import json
    if isinstance(items_json, str):
        items = json.loads(items_json)
    else:
        items = items_json

    if not template_name and company:
        template_name = (
            _default_sales_template(company, gst_type)
            if tax_type == "sales"
            else _default_purchase_template(company, gst_type)
        )

    tax_doctype = "Sales Taxes and Charges Template" if tax_type == "sales" else "Purchase Taxes and Charges Template"

    net_total = sum(flt(it.get("amount", 0)) for it in items)

    taxes = []
    total_tax = 0
    if template_name and frappe.db.exists(tax_doctype, template_name):
        tmpl = frappe.get_doc(tax_doctype, template_name)
        for row in tmpl.taxes:
            amount = 0
            if row.charge_type == "On Net Total" and row.rate:
                amount = net_total * flt(row.rate) / 100
            elif row.charge_type == "Actual":
                amount = flt(row.rate)
            total_tax += amount
            taxes.append({
                "charge_type": row.charge_type,
                "account_head": row.account_head,
                "rate": row.rate,
                "amount": amount,
                "description": row.description,
            })

    return {
        "net_total": net_total,
        "tax_rows": taxes,
        "total_tax": total_tax,
        "grand_total": net_total + total_tax,
        "resolved_template": template_name or "",
    }
