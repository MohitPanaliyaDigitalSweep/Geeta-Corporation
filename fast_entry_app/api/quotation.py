import json
import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from fast_entry_app.api.item import get_invoice_uom as _invoice_uom
from fast_entry_app.api.sales import _apply_manual_sales_taxes, _get_sales_tax_template, _get_tax_account

_get_qt_tax_account = _get_tax_account


@frappe.whitelist()
def create_quotation(data):
    """Create a Quotation (kept in Draft) from fast entry data."""
    if isinstance(data, str):
        data = json.loads(data)

    errors = validate_quotation(data)
    if errors:
        frappe.throw("<br>".join(errors))

    company = data.get("company")
    customer = data.get("customer")
    items = data.get("items", [])

    company_doc = frappe.get_cached_doc("Company", company)
    currency = company_doc.default_currency or "INR"

    qt = frappe.new_doc("Quotation")
    qt.company = company
    qt.quotation_to = "Customer"
    qt.party_name = customer
    qt.order_type = "Sales"
    qt.transaction_date = getdate(data.get("transaction_date") or nowdate())
    qt.valid_till = getdate(data.get("valid_till") or add_days(nowdate(), 30))
    qt.currency = currency
    qt.conversion_rate = 1.0
    qt.naming_series = "SAL-QTN-.YYYY.-"

    selling_price_list = frappe.db.get_value("Selling Settings", None, "selling_price_list")
    if selling_price_list:
        qt.selling_price_list = selling_price_list

    delivery_person = (data.get("delivery_person") or "").strip()
    delivery_vehicle = (data.get("delivery_vehicle") or "").strip()
    sales_person = (data.get("sales_person") or "").strip()

    if delivery_person:
        qt.driver_name = delivery_person
    if delivery_vehicle:
        qt.vehicle_no = delivery_vehicle
    if sales_person:
        qt.fe_sales_person = sales_person
        if frappe.db.exists("Sales Person", sales_person):
            qt.append("sales_team", {
                "sales_person": sales_person,
                "allocated_percentage": 100,
            })

    has_fe_fields = frappe.db.has_column("Quotation Item", "fe_box")
    for item_data in items:
        item_code = str(item_data.get("item_code", "")).strip()
        if not item_code:
            continue

        box = flt(item_data.get("box")) or 0
        pcs = flt(item_data.get("pcs")) or 0
        ltr = flt(item_data.get("ltr")) or 0
        qty = flt(item_data.get("qty")) or 0
        rate = flt(item_data.get("rate")) or 0
        if qty <= 0 or rate <= 0:
            continue

        hsn_code = ""
        if frappe.db.has_column("Item", "gst_hsn_code"):
            hsn_code = frappe.db.get_value("Item", item_code, "gst_hsn_code") or ""

        amount = flt(pcs * rate)
        total_ltr = flt(item_data.get("total_ltr")) or 0
        uom_info = _invoice_uom(item_code)

        item_row = qt.append("items", {
            "item_code": item_code,
            "qty": pcs,
            "rate": rate,
            "amount": amount,
            "uom": uom_info["uom"],
            "conversion_factor": uom_info["conversion_factor"],
            "warehouse": item_data.get("warehouse") or data.get("warehouse") or "",
        })
        if has_fe_fields:
            item_row.fe_box = box
            item_row.fe_pcs = pcs
            item_row.fe_ltr = ltr
            item_row.fe_total_ltr = total_ltr
        if frappe.db.has_column("Quotation Item", "gst_hsn_code"):
            item_row.gst_hsn_code = hsn_code

    discount = flt(data.get("discount")) or 0
    if discount > 0:
        qt.additional_discount_percentage = 0
        qt.discount_amount = discount

    gst_type = data.get("gst_type", "intra")

    tax_override = flt(data.get("tax_override")) or 0
    if tax_override > 0:
        _apply_manual_sales_taxes(qt, company, tax_override, gst_type, company_doc)
    else:
        tax_template = _get_sales_tax_template(company, gst_type)
        if tax_template:
            qt.taxes_and_charges = tax_template
            tmpl = frappe.get_doc("Sales Taxes and Charges Template", tax_template)
            qt.taxes = []
            for row in tmpl.taxes:
                if not row.account_head:
                    continue
                if "reverse" in (row.description or "").lower():
                    continue
                qt.append("taxes", {
                    "charge_type": row.charge_type,
                    "account_head": row.account_head,
                    "description": row.description,
                    "rate": row.rate,
                    "cost_center": row.cost_center or company_doc.cost_center or "",
                })

    freight = flt(data.get("freight")) or 0
    if freight > 0:
        income_account = company_doc.default_income_account or ""
        cost_center = company_doc.cost_center or ""
        qt.append("taxes", {
            "charge_type": "Actual",
            "account_head": income_account,
            "description": "Freight / Transport",
            "rate": 0,
            "amount": freight,
            "cost_center": cost_center,
        })
        cgst_account = _get_qt_tax_account(company, "cgst")
        sgst_account = _get_qt_tax_account(company, "sgst")
        igst_account = _get_qt_tax_account(company, "igst")
        if gst_type == "inter" and igst_account:
            qt.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": igst_account,
                "description": "Freight IGST @ 18%",
                "rate": 18,
                "cost_center": cost_center,
            })
        else:
            if cgst_account:
                qt.append("taxes", {
                    "charge_type": "On Net Total",
                    "account_head": cgst_account,
                    "description": "Freight CGST @ 9%",
                    "rate": 9,
                    "cost_center": cost_center,
                })
            if sgst_account:
                qt.append("taxes", {
                    "charge_type": "On Net Total",
                    "account_head": sgst_account,
                    "description": "Freight SGST @ 9%",
                    "rate": 9,
                    "cost_center": cost_center,
                })

    qt.flags.ignore_permissions = True
    qt.flags.ignore_links = True
    qt.run_method("set_missing_values")
    qt.run_method("calculate_taxes_and_totals")

    qt.insert(ignore_permissions=True)

    return {
        "name": qt.name,
        "status": "Draft",
        "grand_total": qt.grand_total,
    }


@frappe.whitelist()
def validate_quotation(data):
    """Validate quotation data."""
    if isinstance(data, str):
        data = json.loads(data)

    errors = []
    if not data.get("company"):
        errors.append("Company is required")
    if not data.get("customer"):
        errors.append("Customer is required")

    transaction_date = data.get("transaction_date") or nowdate()
    valid_till = data.get("valid_till") or add_days(nowdate(), 30)
    if getdate(valid_till) < getdate(transaction_date):
        errors.append("Valid Till cannot be before Transaction Date")

    items = data.get("items", [])
    valid_items = [i for i in items if i.get("item_code") and flt(i.get("pcs", 0)) > 0]
    if not valid_items:
        errors.append("At least one item with PCS > 0 is required")

    for item in valid_items:
        if flt(item.get("rate", 0)) <= 0:
            errors.append(f"Row {item.get('idx', '?')}: Rate must be greater than 0")

    return errors


@frappe.whitelist()
def get_recent_quotations(limit=20):
    """Get recent quotations with full details for sidebar display."""
    if isinstance(limit, str):
        limit = int(limit)

    quotations = frappe.get_all(
        "Quotation",
        fields=["name", "party_name", "company", "transaction_date", "grand_total", "status", "docstatus"],
        order_by="transaction_date desc, creation desc",
        limit_page_length=limit,
    )

    result = []
    for q in quotations:
        mobile_no = ""
        email_id = ""
        if q.party_name:
            cust = frappe.db.get_value("Customer", q.party_name, ["mobile_no", "email_id"], as_dict=True)
            if cust:
                mobile_no = cust.mobile_no or ""
                email_id = cust.email_id or ""

        # Get items summary
        items = frappe.get_all(
            "Quotation Item",
            filters={"parent": q.name},
            fields=["item_code", "item_name", "qty", "amount"],
            limit_page_length=10,
        )
        items_summary = []
        total_items = frappe.db.count("Quotation Item", {"parent": q.name})
        for it in items:
            items_summary.append({
                "item_code": it.item_code,
                "item_name": it.item_name or it.item_code,
                "qty": it.qty,
                "amount": it.amount,
            })

        result.append({
            "name": q.name,
            "party_name": q.party_name,
            "company": q.company or "",
            "date": str(q.transaction_date) if q.transaction_date else "",
            "grand_total": q.grand_total,
            "status": q.status,
            "docstatus": q.docstatus,
            "mobile_no": mobile_no,
            "email_id": email_id,
            "total_items": total_items,
            "items": items_summary,
        })

    return result
