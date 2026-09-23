# Geeta Corporation — Fast Entry App

ERPNext app (Frappe **v16**) that turns purchase, sales, quotation, payment, stock, ledger and reporting workflows into a fast, keyboard-friendly, single-page experience. Includes custom print formats with e-Invoice / e-Way Bill QR support, Party Group management, and a full BI report suite.

Tested against: frappe `v16.31.0`, erpnext `v16.32.0`, india_compliance `v16.8.3`, hrms `v16.19.0`, print_designer `v1.6.5`.

---

## Features

### Fast entry pages (Sidebar → `Fast Entry`)
| Page | Route | Purpose |
|---|---|---|
| Purchase Entry | `/app/fast-purchase-entry` | Add multiple items quickly, auto amount, GST auto-detect (intra/inter by GSTIN), Discount, Freight (18% GST), WhatsApp/Email with PDF |
| Sales Entry | `/app/fast-sales-entry` | Same fast workflow for Sales Invoices; e-Invoice + e-Way Bill aware |
| Quotation Entry | `/app/fast-quotation-entry` | Fast RFQ; warehouse hidden; send via WhatsApp/Email |
| ICT Entry | `/app/fast-ict-entry` | Inter Company Transfer — creates SO→DN→SI and PO→PR→PI from one screen, propagates `fe_pcs`/`fe_box`/`fe_ltr`, posts amounts = PCS × rate after submit |
| Payment Entry | `/app/fast-payment-entry` | Sales payments. Type amount → oldest unpaid invoices auto-allocated, redistribute on manual tick/untick |
| Bulk/Purchase Payment | `/app/fast-bulk-payment` | Purchase payments (PAY mode), same allocation logic |
| Sales Payment | `/app/fast-sales-payment` | Sales payments (Customer mode) |
| Stock Report | `/app/fast-stock-report` | Consolidated stock from DN/PR/SI/PI items, per-company breakdown via "All Companies" |
| Ledger & P&L | `/app/fast-ledger-pnl` | Party ledger + P&L with live account search |
| Party Groups | `/app/fast-party-group` | Create/manage Party Groups, auto-locks party type, syncs `fe_group` |
| Settings | *Fast Entry Settings* DocType | App settings |

### Reports (BI dashboard)
| Page | Route | Features |
|---|---|---|
| Sales Person Performance | `/app/fast-sales-report` | KPI cards, 6 charts, tables, pincode filter, CSV export |
| Sales Person SP Detail | `/app/fast-sp-detail-report` | MTD/QTD/YTD period comparison, KPIs with sparklines, bar charts (Sales, PCS, Top Products), CSV export |
| Area Potential Report | `/app/fast-area-potential-report` | Pincode-based (Area → Pincode → Party), PCS by pincode, Top Products |
| SP Overdue Report | `/app/fast-sp-overdue-report` | Per sales-person outstanding vs sales, age-of-overdue breakdown |
| Party Group Report | `/app/fast-partygroup-report` | Group → customer rollups, Customers by Group, Top Products |

All 4 enhanced reports: **multi-select filters + MTD/QTD/YTD chips + comparison period dropdown + KPI sparklines + frappe-charts bar charts + CSV export**. Auto-load on open and on filter change (debounced 500 ms).

### Send (WhatsApp / Email)
- WhatsApp: PDF auto-downloads → `wa.me/NUMBER?text=...` opens chat. Server returns `wa_url` + `pdf_url`.
- Email: server sends via SMTP with PDF attached.
- Also enabled on the native **Sales Invoice / Purchase Invoice / Quotation** forms via `erpnext_pi_override.js`.

### Print formats (shipped as fixtures)
- `Custom Sales Invoice` — single-page, Chrome PDF, e-Invoice QR (signed QR), IRN/Ack No/Ack Date, static vehicle details, freight/discount rows, ship-to block.
- `Custom Purchase Invoice`
- `Custom Quotation`
- `Print Invoice 1`

---

## Installation

```bash
bench init --version version-16 frappe-bench
cd frappe-bench
bench setup requirements
bench new-site dev.localhost
bench get-app https://github.com/MohitPanaliyaDigitalSweep/Geeta-Corporation
bench --site dev.localhost install-app fast_entry_app
```

App order used: `frappe, india_compliance, erpnext, hrms, print_designer, fast_entry_app`.

Also install:

```bash
bench get-app https://github.com/frappe/india_compliance --branch version-16
bench get-app https://github.com/frappe/hrms --branch version-16
bench get-app https://github.com/frappe/print_designer --branch version-16
bench --site dev.localhost install-app india_compliance hrms print_designer
```

After install:

```bash
bench --site dev.localhost migrate
bench --site dev.localhost clear-cache
bench build --app fast_entry_app
```

The migrate step:
1. Runs `fast_entry_app.patches.v1_item_table_columns` → creates the `fe_box` / `fe_pcs` / `fe_ltr` / `fe_total_ltr` custom fields on all 7 item tables.
2. Runs `fast_entry_app.patches.migrate_fe_group` → migrates legacy `fe_group` text values into `Party Group` records.
3. Syncs fixtures: 31 `Custom Field`s, `Workspace Sidebar` (19 items), and the 4 `Print Format`s.

---

## Required changes to OTHER apps (nothing is patched — verify instead)

**No source code of frappe / erpnext / india_compliance / hrms / print_designer is modified.** Everything is configured. See [docs/OTHER_APP_CHANGES.md](docs/OTHER_APP_CHANGES.md) for the config checklist, and [docs/SITE_SETUP.md](docs/SITE_SETUP.md) for the exact settings used on the working site.

---

## Project layout

```
fast_entry_app/
├── api/                        # All server-side endpoints
│   ├── sales.py               # Sales entry + autocomplete + taxes
│   ├── purchase.py            # Purchase entry
│   ├── quotation.py           # Quotation entry
│   ├── ict.py                 # Inter Company Transfer
│   ├── payment.py             # Payment allocation engine
│   ├── party.py               # Customer/Supplier details, GST auto-detect
│   ├── party_group.py         # Party Group CRUD + fe_group sync
│   ├── stock_report.py        # Stock (All Companies support)
│   ├── item.py                # Item/UOM lookups
│   ├── ledger_pnl.py          # Ledger + P&L
│   ├── invoice_send.py        # WhatsApp + Email APIs
│   ├── reports.py             # 4 report APIs
│   └── sales_person_report.py # Original SP performance API
├── fast_entry_app/
│   ├── doctype/               # Fast Entry Settings, Inter Company Transfer, Party Group (+children)
│   ├── page/                  # All fast_* pages (json/py/js/css)
│   └── patches/               # v1_item_table_columns, migrate_fe_group
├── fixtures/                  # custom_field.json, workspace_sidebar.json, print_format.json
├── public/js/erpnext_pi_override.js  # WA + Email on native SI/PI/Quotation forms
├── public/css/…               # Page CSS (copied to public/css — see docs)
├── setup_custom_fields.py     # fe_* custom field definitions
└── workspace_sidebar/fast_entry.json
```

---

## Getting support

- ERPNext: https://docs.erpnext.com
- Frappe v16: https://frappeframework.com/docs
- India Compliance: https://github.com/resilient-tech/india-compliance