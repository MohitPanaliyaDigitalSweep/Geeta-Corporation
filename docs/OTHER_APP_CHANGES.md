# Other-App Changes Required

This document lists everything that differs from a stock bench so the **Fast Entry App** behaves exactly like the working Geeta Corporation site.

> **Rule:** None of these touch source code of `frappe`, `erpnext`, `india_compliance`, `hrms`, or `print_designer`. They are **site data / settings**. If you ever need to change upstream source, do it via a new patch in this app and document it here.

---

## 1. App set & versions (verified working)

| App | Version |
|---|---|
| frappe | 16.31.0 |
| erpnext | 16.32.0 |
| india_compliance | 16.8.3 |
| hrms | 16.19.0 |
| print_designer | 1.6.5 |
| fast_entry_app | 0.0.1 |

`sites/apps.txt` order:

```
frappe, india_compliance, erpnext, hrms, print_designer, fast_entry_app
```

---

## 2. Site config (`sites/<site>/site_config.json`)

```json
{
  "developer_mode": 1
}
```

> `developer_mode` matters: it enables Workspace Sidebar file export (`workspace_sidebar/fast_entry.json`), Page name handling, and fixture export. The working bench also runs `gunicorn_workers: 25`, `webserver_port: 8000`.

---

## 3. Custom Fields — shipped as fixtures (no manual work)

31 `Custom Field`s (module `Fast Entry App`) installed automatically via `fixtures/custom_field.json`:

- **7 item tables**: `Purchase Invoice Item`, `Sales Invoice Item`, `Quotation Item`, `Sales Order Item`, `Purchase Order Item`, `Delivery Note Item`, `Purchase Receipt Item` each get:
  - `fe_box` (Float), `fe_pcs` (Float), `fe_ltr` (Float), `fe_total_ltr` (Float)
- `Sales Invoice` / `Purchase Invoice`: `fe_group`, `fe_sales_person`
- `Customer` / `Supplier`: `fe_group`
- `Item`: `fe_pcs`, `fe_box`, `fe_ltr` (UOM-friendly inputs)
- Plus a dependent-field patch (`v1_item_table_columns`) that wires `fe_box`/`fe_pcs`/`fe_ltr`/`fe_total_ltr` with defaults.

### UOM conversion — DO NOT CHANGE
On the working site **Item `2900145`**:
```
Nos = 200.0, Litre = 0.06, Box = 1.0   (stock_uom)
```
Also the **Box** UOM has **`must_be_whole_number = 0`** (set on the `UOM` record via desk) so boxes can hold fractional values.

---

## 4. Print Formats (shipped as fixtures)

Installed from `fixtures/print_format.json`:

- `Custom Sales Invoice` → Sales Invoice
- `Custom Purchase Invoice` → Purchase Invoice
- `Custom Quotation` → Quotation
- `Print Invoice 1` → Purchase Invoice

Each is `Jinja`, `pdf_generator: "chrome"`. They render:
- e-Invoice **QR code** / IRN / Ack No / Ack Date from `E Invoice Log` (`signed_qr_code` base64 PNG)
- static vehicle details `GJ05BX9053, GJ05BZ9976, GJ05CU2271, GJ05CW4572, Transport`
- party block from `customer_address`/`supplier_address` with 36-char street truncation
- ship-to = Geeta Corporation (from `company_address`/`billing_address` phone)

**If a print format imports as blank**, clear cache and re-`migrate`.

---

## 5. Workspace Sidebar (`Fast Entry` — 19 items)

Installed from fixture + `workspace_sidebar/fast_entry.json`. Order matters, icons included:

```
1  Purchase Entry         Page fast-purchase-entry
2  Sales Entry            Page fast-sales-entry
3  ICT Entry              Page fast-ict-entry
4  Payment Entry          Page fast-payment-entry
5  Purchase Payment       Page fast-bulk-payment
6  Sales Payment          Page fast-sales-payment
7  Stock Report           Page fast-stock-report
8  Ledger & P&L           Page fast-ledger-pnl
9  Settings               DocType Fast Entry Settings
10 ICT List               DocType Inter Company Transfer
11 Quotation              Page fast-quotation-entry
12 Party Groups           Page fast-party-group
13 Purchase Invoices      DocType Purchase Invoice
14 Sales Invoices         DocType Sales Invoice
15 Sales Person Performance   Page fast-sales-report
16 Sales Person SP Detail      Page fast-sp-detail-report
17 Area Potential Report       Page fast-area-potential-report
18 SP Overdue Report           Page fast-sp-overdue-report
19 Party Group Report          Page fast-partygroup-report
```

> ⚠️ After installing **HRMS** or **print_designer**, the sidebar can be re-created from the platform and drop the 4 report entries (rows 16–19). **Re-run migrate** (fixtures restore) or re-add the 4 links via desk. Report pages themselves are registered from the app's `page/*` folders.

---

## 6. Page registration & known Frappe v16 quirks (workarounds already in-app)

- **Pages** are registered by the `page/*` folders and inserted into `tabPage` on migrate. No manual step.
- **Breadcrumbs**: `frappe.breadcrumbs.add(...)` must be called in `on_page_load` *before* the page class instantiation — already handled in every page JS.
- **`frappe.prompt` bug (v16)**: on submit it clears the field values; all send dialogs (WhatsApp/Email) use `frappe.ui.Dialog` instead — already handled.
- **CSS in page folders isn't bundled**: page `.css` files must also live in `public/css/` (and are listed in `hooks.app_include_css`). On upgrade, re-copy: `cp page/<name>/<name>.css public/css/<name>.css` (this is already the committed state).
- **`frappe-charts` option key** is `type` (NOT `chartType`) — the chart helpers inside `report_ui_components.js` use `type`.

---

## 7. GST / india_compliance settings (desk: GST Settings)

Used for sandbox e-Invoice + e-Way Bill testing:

| Setting | Value |
|---|---|
| `enable_e_invoice` | ✅ |
| `enable_e_waybill` | ✅ |
| `sandbox_mode` | ✅ |
| `generate_e_waybill_with_e_invoice` | ✅ |
| `auto_generate_e_invoice` | ✅ |
| `api_secret` | `test_sandbox_api_key` (sandbox; enables `is_api_enabled()`) |

No real NIC credentials needed — `india_compliance.gst_india.api_classes.nic.e_invoice.EnrichedEInvoiceAPI` ships its own sandbox test credentials; base URL `https://asp.resilient.tech`.

> ⚠️ If `E Invoice Log` doesn't exist on a fresh site, it is created by india_compliance migrate itself — cross-check it under GST India. The print format reads it via `frappe.db.get_value('E Invoice Log', {'reference_name': doc.name, ...}, ['signed_qr_code','irn','acknowledgement_number','acknowledged_on'])`.

### GST tax templates used by GST auto-detection
State is inferred from GSTIN first 2 digits:
- same state → **Output GST In-state - GC** (`SGST 9%` + `CGST 9%`)
- different state → **Output GST Out-state - GC** (`IGST 18%`)

ICT requires the party GST category **`Registered Regular`** (not `Registered`).

---

## 8. Email (desk: Email Account)

Create the `Brevo SMTP` email account and set it as **default outgoing**:

| Field | Value |
|---|---|
| Email Account | `Brevo SMTP` |
| SMTP Server | `smtp-relay.brevo.com` |
| SMTP Port | `587` |
| Use SSL/TLS | TLS |
| SMTP Login / Password | your Brevo SMTP key |
| Is Default | ✅ |

Used by `frappe.sendmail()` in the Email send flow.

---

## 9. PDF rendering

- Print formats use `pdf_generator = "chrome"` (Frappe **Chrome**). The bench has headless shell at `bench/chromium/chrome-linux/headless_shell` (set up automatically by frappe's chromium helper; ran on first PDF generation).
- No `wkhtmltopdf` needed.

---

## 10. Sales Person data model used by reports

- Sales Persons on the working site: `Imran Sales Boy` (enabled), `Mohit Sales Person`, `Sales Team`.
- Reports read sales-person from **Sales Team** child rows + `fe_sales_person` on Sales Invoice.
- Pincodes exist on Address records (11 pincodes in test data).

---

## 11. Optional test data

`scripts/generate_test_data.py` (in this repo) creates: 20 customers, 2 Party Groups, 190 SIs, 124 DNs, 30 ICTs across Jan 2024 → Sep 2026. Run on the installed site for report/demo data.