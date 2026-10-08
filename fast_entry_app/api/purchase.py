import json
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from fast_entry_app.api.item import get_invoice_uom as _invoice_uom
from fast_entry_app.api.item import get_item_uom as _pack_factors


@frappe.whitelist()
def create_purchase_invoice(data):
    """Create and submit a Purchase Invoice from fast entry data."""
    if isinstance(data, str):
        data = json.loads(data)

    # Validate
    errors = validate_purchase_invoice(data)
    if errors:
        frappe.throw("<br>".join(errors))

    company = data.get("company")
    supplier = data.get("supplier")
    items = data.get("items", [])

    # Get company defaults
    company_doc = frappe.get_cached_doc("Company", company)
    credit_to = company_doc.default_payable_account
    if not credit_to:
        frappe.throw(_("No default Payable Account set for {0}").format(company))

    currency = company_doc.default_currency or "INR"

    # Build Purchase Invoice
    pi = frappe.new_doc("Purchase Invoice")
    pi.company = company
    pi.supplier = supplier
    pi.posting_date = getdate(data.get("posting_date") or nowdate())
    pi.bill_no = data.get("bill_no")
    pi.bill_date = getdate(data.get("bill_date") or data.get("posting_date") or nowdate())
    pi.due_date = getdate(data.get("bill_date") or nowdate())
    pi.credit_to = credit_to
    pi.currency = currency
    pi.conversion_rate = 1.0
    pi.naming_series = "PINV-.YY.-"

    # Buying price list
    buying_price_list = frappe.db.get_value("Buying Settings", None, "buying_price_list")
    if buying_price_list:
        pi.buying_price_list = buying_price_list

    # Set warehouse at header level if provided
    if data.get("warehouse"):
        pi.set_warehouse = data.get("warehouse")

    # Create stock impact (purchase receipt + stock entry) on submit when enabled
    if data.get("update_stock"):
        pi.update_stock = 1

    # Append items
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

        # Item master fallbacks (UOM conversions + optional legacy pack fields).
        # The custom_* columns are hand-added on some sites only, so they are
        # read defensively; the invoice itself always stores fe_*.
        item_master = {}
        if frappe.db.has_column("Item", "custom_box"):
            item_master = frappe.db.get_value(
                "Item", item_code, ["custom_box", "custom_ltr"], as_dict=True
            ) or {}
        uoms = _pack_factors(item_code)
        nos_factor = uoms["nos_factor"]
        litre_factor = uoms["litre_factor"]
        nos_factor = flt(item_data.get("nos_factor")) or nos_factor
        litre_factor = flt(item_data.get("litre_factor")) or litre_factor

        if not box:
            box = flt(item_master.get("custom_box")) or flt(pcs / nos_factor)
        if not pcs and box:
            pcs = flt(box * nos_factor)
        if not ltr:
            ltr = flt(item_master.get("custom_ltr")) or litre_factor
        total_ltr = flt(item_data.get("total_ltr")) or flt(pcs * ltr)

        hsn_code = ""
        if frappe.db.has_column("Item", "gst_hsn_code"):
            hsn_code = frappe.db.get_value("Item", item_code, "gst_hsn_code") or ""
        amount = flt(pcs * rate)
        uom_info = _invoice_uom(item_code)

        item_row = pi.append("items", {
            "item_code": item_code,
            "qty": pcs,
            "rate": rate,
            "amount": amount,
            "uom": uom_info["uom"],
            "conversion_factor": uom_info["conversion_factor"],
            "stock_qty": pcs,
            "warehouse": item_data.get("warehouse") or data.get("warehouse") or "",
            "fe_box": box,
            "fe_pcs": pcs,
            "fe_ltr": ltr,
            "fe_total_ltr": total_ltr,
        })
        if frappe.db.has_column("Purchase Invoice Item", "gst_hsn_code"):
            item_row.gst_hsn_code = hsn_code

    # Apply discount
    discount = flt(data.get("discount")) or 0
    if discount > 0:
        pi.additional_discount_percentage = 0
        pi.discount_amount = discount
        # Discount mode comes from the UI ("Net Total" default) — see sales.py.
        apply_on = (data.get("apply_discount_on") or "Net Total").strip()
        if apply_on not in ("Net Total", "Grand Total"):
            frappe.throw(_("Apply Discount On must be Net Total or Grand Total"))
        pi.apply_discount_on = apply_on

    # Freight goes FIRST when present (see the note below): the GST rows are
    # written as "On Previous Row Total" pointing at it, so GST covers items
    # + freight.
    freight = flt(data.get("freight")) or 0
    freight_row_idx = 0
    if freight > 0:
        expense_account = company_doc.default_expense_account or ""
        cost_center = company_doc.cost_center or ""
        pi.append("taxes", {
            "charge_type": "Actual",
            "account_head": expense_account,
            "description": "Freight / Transport",
            "rate": 0,
            # NOTE: the child-table amount field is `tax_amount`; `amount`
            # is not a column and is silently ignored (freight used to book 0).
            "tax_amount": freight,
            "cost_center": cost_center,
        })
        freight_row_idx = 1

    # Apply tax template. When freight is present the copied "On Net Total"
    # rows become "On Previous Row Total" -> freight row, so GST covers items
    # + freight. (A separate "On Net Total" freight-GST row would compute on
    # the invoice subtotal instead of the freight, and duplicate CGST/SGST
    # accounts break India Compliance's item-wise GST validation.)
    tax_override = flt(data.get("tax_override")) or 0
    if tax_override > 0:
        _apply_manual_taxes(pi, company, tax_override, data.get("gst_type", "intra"), company_doc, freight_row_idx)
    else:
        tax_template = _get_tax_template(company, data.get("gst_type"))
        if tax_template:
            pi.taxes_and_charges = tax_template
            tmpl = frappe.get_doc("Purchase Taxes and Charges Template", tax_template)
            if not freight_row_idx:
                pi.taxes = []
            for row in tmpl.taxes:
                if not row.account_head:
                    continue
                if "reverse" in (row.description or "").lower():
                    continue
                charge_type = row.charge_type
                row_id = row.row_id
                if freight_row_idx and charge_type == "On Net Total":
                    charge_type = "On Previous Row Total"
                    row_id = freight_row_idx
                elif row_id:
                    # Freight row prepended above shifts template row indexes.
                    row_id = flt(row_id) + freight_row_idx
                pi.append("taxes", {
                    "charge_type": charge_type,
                    "row_id": row_id,
                    "account_head": row.account_head,
                    "description": row.description,
                    "rate": row.rate,
                    "cost_center": row.cost_center or company_doc.cost_center or "",
                })

    # Set missing values (auto-fills accounts, etc.)
    pi.flags.ignore_permissions = True
    pi.flags.ignore_links = True
    pi.run_method("set_missing_values")
    pi.run_method("calculate_taxes_and_totals")

    # Insert and submit
    pi.insert(ignore_permissions=True)
    pi.submit()

    return {
        "name": pi.name,
        "status": "Submitted",
        "grand_total": pi.grand_total,
        "outstanding_amount": pi.outstanding_amount,
    }


@frappe.whitelist()
def validate_purchase_invoice(data):
    """Validate purchase invoice data. Returns list of errors."""
    if isinstance(data, str):
        data = json.loads(data)

    errors = []

    if not data.get("company"):
        errors.append("Company is required")
    if not data.get("supplier"):
        errors.append("Supplier is required")
    if not data.get("bill_no"):
        errors.append("Bill No is required")
    if not data.get("bill_date"):
        errors.append("Bill Date is required")

    if data.get("update_stock") and not data.get("warehouse"):
        errors.append("Warehouse is required for stock impact")

    items = data.get("items", [])
    valid_items = [i for i in items if i.get("item_code") and flt(i.get("pcs", 0)) > 0]

    if not valid_items:
        errors.append("At least one item with PCS > 0 is required")

    for item in valid_items:
        if flt(item.get("rate", 0)) <= 0:
            errors.append(f"Row {item.get('idx', '?')}: Rate must be greater than 0")

    # Check duplicate bill
    if data.get("supplier") and data.get("bill_no"):
        existing = frappe.db.exists(
            "Purchase Invoice",
            {
                "supplier": data["supplier"],
                "bill_no": data["bill_no"],
                "docstatus": 1,
            },
        )
        if existing:
            errors.append(f"Bill No {data['bill_no']} already exists for this supplier (Invoice: {existing})")

    return errors


@frappe.whitelist()
def get_last_invoices(supplier, limit=5):
    """Get last N invoices for a supplier."""
    if not supplier:
        return []

    invoices = frappe.get_list(
        "Purchase Invoice",
        filters={"supplier": supplier, "docstatus": 1},
        fields=["name", "posting_date", "grand_total", "bill_no"],
        order_by="creation desc",
        limit_page_length=int(limit),
    )

    for inv in invoices:
        items = frappe.get_list(
            "Purchase Invoice Item",
            filters={"parent": inv.name},
            fields=["item_code", "item_name", "qty", "rate", "amount"],
        )
        inv["items"] = items

    return invoices


def _get_pi_tax_account(company, tax_type):
    """Get Input CGST/SGST/IGST account for a company (never Refund/RCM)."""
    maps = {
        "cgst": "Input Tax CGST",
        "sgst": "Input Tax SGST",
        "igst": "Input Tax IGST",
    }
    prefix = maps.get(tax_type, "")
    if not prefix:
        return ""
    account = frappe.db.get_value(
        "Account",
        [
            ["company", "=", company],
            ["account_name", "like", f"%{prefix}%"],
            ["account_name", "not like", "%RCM%"],
            ["account_name", "not like", "%Refund%"],
        ],
        "name",
    )
    return account or ""


def _get_tax_template(company, gst_type="intra"):
    """Get the appropriate tax template for the company and GST type (exclude RCM)."""
    keyword = "In-state" if gst_type == "intra" else "Out-state"
    templates = frappe.get_all(
        "Purchase Taxes and Charges Template",
        filters=[
            ["company", "=", company],
            ["title", "like", f"%{keyword}%"],
            ["title", "not like", "%RCM%"],
        ],
        fields=["name"],
        limit_page_length=1,
    )
    template = templates[0].name if templates else None

    if not template:
        templates = frappe.get_all(
            "Purchase Taxes and Charges Template",
            filters=[
                ["company", "=", company],
                ["title", "not like", "%RCM%"],
            ],
            fields=["name"],
            limit_page_length=1,
        )
        template = templates[0].name if templates else None

    return template


def _apply_manual_taxes(pi, company, tax_rate, gst_type, company_doc, freight_row_idx=0):
    """Apply manual GST tax rows when user selects a tax override rate.

    When freight is present (freight_row_idx > 0) the rows point at it via
    "On Previous Row Total" so GST covers items + freight.
    """
    pi.taxes_and_charges = ""
    charge_type = "On Previous Row Total" if freight_row_idx else "On Net Total"
    row_id = freight_row_idx or None

    if gst_type == "inter":
        account = frappe.db.get_value(
            "Account",
            [
                ["company", "=", company],
                ["account_name", "like", "%Input Tax IGST%"],
                ["account_name", "not like", "%RCM%"],
                ["account_name", "not like", "%Refund%"],
            ],
            "name",
        )
        if not account:
            frappe.throw(_("No IGST account found for {0}. Please set up tax accounts.").format(company))
        pi.append("taxes", {
            "charge_type": charge_type,
            "row_id": row_id,
            "account_head": account,
            "description": f"IGST @ {tax_rate}%",
            "rate": tax_rate,
            "cost_center": company_doc.cost_center or "",
        })
    else:
        cgst_account = frappe.db.get_value(
            "Account",
            [
                ["company", "=", company],
                ["account_name", "like", "%Input Tax CGST%"],
                ["account_name", "not like", "%RCM%"],
                ["account_name", "not like", "%Refund%"],
            ],
            "name",
        )
        sgst_account = frappe.db.get_value(
            "Account",
            [
                ["company", "=", company],
                ["account_name", "like", "%Input Tax SGST%"],
                ["account_name", "not like", "%RCM%"],
                ["account_name", "not like", "%Refund%"],
            ],
            "name",
        )
        if not cgst_account or not sgst_account:
            frappe.throw(_("No CGST/SGST accounts found for {0}. Please set up tax accounts.").format(company))
        half_rate = tax_rate / 2
        pi.append("taxes", {
            "charge_type": charge_type,
            "row_id": row_id,
            "account_head": cgst_account,
            "description": f"CGST @ {half_rate}%",
            "rate": half_rate,
            "cost_center": company_doc.cost_center or "",
        })
        pi.append("taxes", {
            "charge_type": charge_type,
            "row_id": row_id,
            "account_head": sgst_account,
            "description": f"SGST @ {half_rate}%",
            "rate": half_rate,
            "cost_center": company_doc.cost_center or "",
        })
