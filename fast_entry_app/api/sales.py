import hashlib
import json
import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

from fast_entry_app.api.item import get_invoice_uom as _invoice_uom
from fast_entry_app.api.item import get_item_uom as _pack_factors

# Reject duplicate submissions within this window (seconds). Prevents
# repeated Save clicks from creating multiple identical invoices.
FAST_ENTRY_DEDUP_WINDOW = 120


@frappe.whitelist()
def fast_entry_context():
    """Companies + default sales person for the logged-in user (HRMS PWA)."""
    companies = frappe.get_all(
        "Company", fields=["name"], limit_page_length=100, order_by="name asc"
    )
    company_list = []
    for c in companies or []:
        name = c.get("name")
        company_list.append(
            {
                "name": name,
                "tax_rate": _company_tax_rate(name),
            }
        )
    return {
        "companies": [c.get("name") for c in companies or []],
        "company_tax_rates": {c["name"]: c["tax_rate"] for c in company_list},
        "default_sales_person": _default_sales_person(),
    }


def _company_tax_rate(company, gst_type="intra"):
    """Half-of-total GST rate from the company's default Sales Tax Template (CGST+SGST halved)."""
    try:
        import india_compliance  # noqa: F401
    except ImportError:
        pass
    template = _get_sales_tax_template(company, gst_type)
    if not template:
        return 0.0
    doc = frappe.get_cached_doc("Sales Taxes and Charges Template", template)
    rate = 0.0
    for row in doc.get("taxes") or []:
        if row.get("rate"):
            rate += flt(row.rate)
    return rate


def _default_sales_person():
    """Best-effort default Sales Person for the logged-in user.

    Resolution order:
    1. A Sales Person whose name matches the session user's name/full_name.
    2. The first enabled, non-group Sales Person (alphabetical).
    """
    user = frappe.session.user
    candidates = frappe.get_all(
        "Sales Person",
        filters={"is_group": 0, "enabled": 1},
        fields=["name", "sales_person_name"],
        order_by="sales_person_name asc",
    )
    if not candidates:
        return ""

    full_name = ""
    if user:
        full_name = frappe.db.get_value("User", user, "full_name") or ""

    user_l = user.lower()
    full_l = (full_name or "").lower()
    for c in candidates:
        hay = ((c.sales_person_name or "") or c.name).lower()
        if user_l and user_l in hay:
            return c.sales_person_name or c.name
        if full_l and full_l in hay:
            return c.sales_person_name or c.name

    first = candidates[0]
    return first.sales_person_name or first.name


@frappe.whitelist()
def create_sales_invoice(data):
    """Create and submit a Sales Invoice from fast entry data."""
    if isinstance(data, str):
        data = json.loads(data)

    errors = validate_sales_invoice(data)
    if errors:
        frappe.throw("<br>".join(errors))

    dedup_key = _invoice_dedup_key(data)
    duplicate = _find_duplicate_invoice(dedup_key)
    if duplicate:
        return {
            "name": duplicate.get("name"),
            "status": "Draft" if duplicate.get("docstatus") == 0 else "Submitted",
            "grand_total": duplicate.get("grand_total"),
            "outstanding_amount": duplicate.get("outstanding_amount"),
            "duplicate": True,
        }

    company = data.get("company")
    customer = data.get("customer")
    draft = 1 if data.get("draft") else 0
    auto_einvoice = 1 if data.get("auto_einvoice") else 0
    auto_ewaybill = 1 if data.get("auto_ewaybill") else 0
    items = data.get("items", [])

    company_doc = frappe.get_cached_doc("Company", company)
    debit_to = company_doc.default_receivable_account
    if not debit_to:
        frappe.throw(_("No default Receivable Account set for {0}").format(company))

    currency = company_doc.default_currency or "INR"

    si = frappe.new_doc("Sales Invoice")
    si.company = company
    si.customer = customer
    si.posting_date = getdate(data.get("posting_date") or nowdate())
    si.due_date = getdate(data.get("due_date") or data.get("posting_date") or nowdate())
    si.debit_to = debit_to
    si.currency = currency
    si.conversion_rate = 1.0
    si.naming_series = "SINV-.YY.-"

    selling_price_list = frappe.db.get_value("Selling Settings", None, "selling_price_list")
    if selling_price_list:
        si.selling_price_list = selling_price_list

    if data.get("warehouse"):
        si.set_warehouse = data.get("warehouse")

    # Create stock impact (delivery note + stock entry) on submit when enabled
    if data.get("update_stock"):
        si.update_stock = 1

    delivery_person = (data.get("delivery_person") or "").strip()
    delivery_vehicle = (data.get("delivery_vehicle") or "").strip()
    sales_person = (data.get("sales_person") or "").strip()

    if delivery_person:
        si.driver_name = delivery_person
        if frappe.db.exists("Driver", delivery_person):
            si.driver = delivery_person
    if delivery_vehicle:
        si.vehicle_no = delivery_vehicle
    if data.get("distance") or data.get("distance") == 0:
        distance = flt(data.get("distance"))
        if distance > 0 and frappe.db.has_column("Sales Invoice", "distance"):
            si.distance = distance
    if sales_person:
        si.fe_sales_person = sales_person
        if frappe.db.exists("Sales Person", sales_person):
            si.append("sales_team", {
                "sales_person": sales_person,
                "allocated_percentage": 100,
            })

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

        item_row = si.append("items", {
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
        if frappe.db.has_column("Sales Invoice Item", "gst_hsn_code"):
            item_row.gst_hsn_code = hsn_code

    discount = flt(data.get("discount")) or 0
    if discount > 0:
        si.additional_discount_percentage = 0
        si.discount_amount = discount

    tax_override = flt(data.get("tax_override")) or 0
    if tax_override > 0:
        _apply_manual_sales_taxes(si, company, tax_override, data.get("gst_type", "intra"), company_doc)
    else:
        tax_template = _get_sales_tax_template(company, data.get("gst_type"))
        if tax_template:
            si.taxes_and_charges = tax_template
            tmpl = frappe.get_doc("Sales Taxes and Charges Template", tax_template)
            si.taxes = []
            for row in tmpl.taxes:
                if not row.account_head:
                    continue
                if "reverse" in (row.description or "").lower():
                    continue
                si.append("taxes", {
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
        si.append("taxes", {
            "charge_type": "Actual",
            "account_head": income_account,
            "description": "Freight / Transport",
            "rate": 0,
            "amount": freight,
            "cost_center": cost_center,
        })
        gst_type = data.get("gst_type", "intra")
        cgst_account = _get_tax_account(company, "cgst")
        sgst_account = _get_tax_account(company, "sgst")
        igst_account = _get_tax_account(company, "igst")
        if gst_type == "inter" and igst_account:
            si.append("taxes", {
                "charge_type": "On Net Total",
                "account_head": igst_account,
                "description": "Freight IGST @ 18%",
                "rate": 18,
                "cost_center": cost_center,
            })
        else:
            if cgst_account:
                si.append("taxes", {
                    "charge_type": "On Net Total",
                    "account_head": cgst_account,
                    "description": "Freight CGST @ 9%",
                    "rate": 9,
                    "cost_center": cost_center,
                })
            if sgst_account:
                si.append("taxes", {
                    "charge_type": "On Net Total",
                    "account_head": sgst_account,
                    "description": "Freight SGST @ 9%",
                    "rate": 9,
                    "cost_center": cost_center,
                })

    si.flags.ignore_permissions = True
    si.flags.ignore_links = True
    si.run_method("set_missing_values")
    si.run_method("calculate_taxes_and_totals")

    if dedup_key:
        si.fe_dedup_key = dedup_key

    si.insert(ignore_permissions=True)

    if draft:
        frappe.db.commit()
        return {
            "name": si.name,
            "status": "Draft",
            "docstatus": 0,
            "grand_total": si.grand_total,
            "outstanding_amount": si.outstanding_amount,
        }

    si.submit()

    if auto_einvoice or auto_ewaybill:
        frappe.db.commit()

    if auto_einvoice:
        try:
            from india_compliance.exceptions import AlreadyGeneratedError
            from india_compliance.gst_india.utils.e_invoice import generate_e_invoice

            generate_e_invoice(si.name)
        except ImportError:
            frappe.log_error(f"india_compliance not installed — cannot generate e-Invoice for {si.name}")
        except AlreadyGeneratedError:
            pass
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Fast Entry: e-Invoice generation failed for {si.name}",
            )

    if auto_ewaybill:
        try:
            from india_compliance.exceptions import AlreadyGeneratedError
            from india_compliance.gst_india.utils.e_waybill import generate_e_waybill

            generate_e_waybill(doctype="Sales Invoice", docname=si.name)
        except ImportError:
            frappe.log_error(f"india_compliance not installed — cannot generate e-Waybill for {si.name}")
        except AlreadyGeneratedError:
            pass
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Fast Entry: e-Waybill generation failed for {si.name}",
            )

    return {
        "name": si.name,
        "status": "Submitted",
        "grand_total": si.grand_total,
        "outstanding_amount": si.outstanding_amount,
    }


@frappe.whitelist()
def validate_sales_invoice(data):
    """Validate sales invoice data."""
    if isinstance(data, str):
        data = json.loads(data)

    errors = []
    if not data.get("company"):
        errors.append("Company is required")
    if not data.get("customer"):
        errors.append("Customer is required")
    if not data.get("invoice_date"):
        errors.append("Invoice Date is required")

    if data.get("update_stock") and not data.get("warehouse"):
        errors.append("Warehouse is required for stock impact")

    items = data.get("items", [])
    valid_items = [i for i in items if i.get("item_code") and flt(i.get("pcs", 0)) > 0]
    if not valid_items:
        errors.append("At least one item with PCS > 0 is required")

    for item in valid_items:
        if flt(item.get("rate", 0)) <= 0:
            errors.append(f"Row {item.get('idx', '?')}: Rate must be greater than 0")

    return errors


@frappe.whitelist()
def get_last_invoices(customer, limit=5):
    """Get last N invoices for a customer."""
    if not customer:
        return []

    invoices = frappe.get_list(
        "Sales Invoice",
        filters={"customer": customer, "docstatus": 1},
        fields=["name", "posting_date", "grand_total"],
        order_by="creation desc",
        limit_page_length=int(limit),
    )

    for inv in invoices:
        items = frappe.get_list(
            "Sales Invoice Item",
            filters={"parent": inv.name},
            fields=["item_code", "item_name", "qty", "rate", "amount"],
        )
        inv["items"] = items

    return invoices


def _get_tax_account(company, tax_type):
    """Get CGST/SGST/IGST account for a company."""
    maps = {
        "cgst": "Output Tax CGST",
        "sgst": "Output Tax SGST",
        "igst": "Output Tax IGST",
    }
    prefix = maps.get(tax_type, "")
    if not prefix:
        return ""
    account = frappe.db.get_value("Account", {"company": company, "account_name": ["like", f"%{prefix}%"]}, "name")
    return account or ""


def _get_sales_tax_template(company, gst_type="intra"):
    """Get the appropriate sales tax template (exclude RCM)."""
    keyword = "In-state" if gst_type == "intra" else "Out-state"
    templates = frappe.get_all(
        "Sales Taxes and Charges Template",
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
            "Sales Taxes and Charges Template",
            filters=[
                ["company", "=", company],
                ["title", "not like", "%RCM%"],
            ],
            fields=["name"],
            limit_page_length=1,
        )
        template = templates[0].name if templates else None

    return template


def _apply_manual_sales_taxes(si, company, tax_rate, gst_type, company_doc):
    """Apply manual GST tax rows for sales when user selects a tax override rate."""
    si.taxes_and_charges = ""

    if gst_type == "inter":
        account = frappe.db.get_value(
            "Account",
            [
                ["company", "=", company],
                ["account_name", "like", "%Output Tax IGST%"],
                ["account_name", "not like", "%RCM%"],
                ["account_name", "not like", "%Refund%"],
            ],
            "name",
        )
        if not account:
            frappe.throw(_("No IGST account found for {0}. Please set up tax accounts.").format(company))
        si.append("taxes", {
            "charge_type": "On Net Total",
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
                ["account_name", "like", "%Output Tax CGST%"],
                ["account_name", "not like", "%RCM%"],
                ["account_name", "not like", "%Refund%"],
            ],
            "name",
        )
        sgst_account = frappe.db.get_value(
            "Account",
            [
                ["company", "=", company],
                ["account_name", "like", "%Output Tax SGST%"],
                ["account_name", "not like", "%RCM%"],
                ["account_name", "not like", "%Refund%"],
            ],
            "name",
        )
        if not cgst_account or not sgst_account:
            frappe.throw(_("No CGST/SGST accounts found for {0}. Please set up tax accounts.").format(company))
        half_rate = tax_rate / 2
        si.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": cgst_account,
            "description": f"CGST @ {half_rate}%",
            "rate": half_rate,
            "cost_center": company_doc.cost_center or "",
        })
        si.append("taxes", {
            "charge_type": "On Net Total",
            "account_head": sgst_account,
            "description": f"SGST @ {half_rate}%",
            "rate": half_rate,
            "cost_center": company_doc.cost_center or "",
        })


@frappe.whitelist()
def search_drivers(search=None, limit=10):
    """Search Driver doctype (delivery persons) by name."""
    limit = int(limit)
    like = f"%{search}%" if search else "%%"
    rows = frappe.get_all(
        "Driver",
        filters=[["full_name", "like", like]],
        fields=["name", "full_name", "cell_number"],
        order_by="full_name asc",
        limit_page_length=limit,
    )
    return [
        {
            "name": r["name"],
            "label": r["full_name"] or r["name"],
            "cell_number": r.get("cell_number") or "",
        }
        for r in rows
    ]


@frappe.whitelist()
def search_vehicles(search=None, limit=10):
    """Search Vehicle doctype by license plate."""
    limit = int(limit)
    like = f"%{search}%" if search else "%%"
    rows = frappe.get_all(
        "Vehicle",
        filters=[["license_plate", "like", like]],
        fields=["name", "license_plate", "make", "model"],
        order_by="license_plate asc",
        limit_page_length=limit,
    )
    return [
        {
            "name": r["name"],
            "label": r["license_plate"],
            "make": r.get("make") or "",
            "model": r.get("model") or "",
        }
        for r in rows
    ]


@frappe.whitelist()
def search_sales_persons(search=None, limit=10):
    """Search Sales Person doctype by name."""
    limit = int(limit)
    like = f"%{search}%" if search else "%%"
    rows = frappe.get_all(
        "Sales Person",
        filters=[["sales_person_name", "like", like]],
        fields=["name", "sales_person_name"],
        order_by="sales_person_name asc",
        limit_page_length=limit,
    )
    return [
        {
            "name": r["name"],
            "label": r["sales_person_name"] or r["name"],
        }
        for r in rows
    ]


def _invoice_dedup_key(data):
    """Stable fingerprint of an invoice payload used to de-duplicate save clicks.

    Built from the business-critical fields only (not UI flags like draft/
    auto_einvoice). Items are sorted by item_code so row order is ignored.
    """
    items = []
    for it in data.get("items") or []:
        item_code = str(it.get("item_code") or "").strip()
        if not item_code:
            continue
        items.append(
            {
                "item_code": item_code,
                "box": flt(it.get("box")),
                "pcs": flt(it.get("pcs")),
                "ltr": flt(it.get("ltr")),
                "rate": flt(it.get("rate")),
            }
        )
    if not items:
        return ""

    items.sort(key=lambda i: i["item_code"])

    canonical = {
        "company": (data.get("company") or "").strip(),
        "customer": (data.get("customer") or "").strip(),
        "posting_date": str(getdate(data.get("posting_date") or data.get("invoice_date") or nowdate())),
        "gst_type": (data.get("gst_type") or "").lower(),
        "tax_override": flt(data.get("tax_override")),
        "warehouse": (data.get("warehouse") or "").strip(),
        "update_stock": 1 if data.get("update_stock") else 0,
        "discount": flt(data.get("discount")),
        "freight": flt(data.get("freight")),
        "distance": flt(data.get("distance")),
        "delivery_person": (data.get("delivery_person") or "").strip(),
        "delivery_vehicle": (data.get("delivery_vehicle") or "").strip(),
        "sales_person": (data.get("sales_person") or "").strip(),
        "items": items,
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _find_duplicate_invoice(dedup_key):
    """Return a recently-created invoice with the same dedup key, if any."""
    if not dedup_key or not frappe.db.has_column("Sales Invoice", "fe_dedup_key"):
        return None

    cutoff = frappe.utils.add_to_date(
        frappe.utils.now_datetime(), seconds=-FAST_ENTRY_DEDUP_WINDOW
    )
    rows = frappe.db.get_all(
        "Sales Invoice",
        filters={
            "fe_dedup_key": dedup_key,
            "docstatus": ["in", [0, 1]],
            "creation": [">=", cutoff],
        },
        fields=["name", "docstatus", "grand_total", "outstanding_amount"],
        order_by="creation desc",
        limit_page_length=1,
    )
    return rows[0] if rows else None
